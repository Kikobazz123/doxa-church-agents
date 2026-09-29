"""Text to MP3: Gemini TTS first (Nigerian-accent style prompt), then edge-tts, then Piper (offline)."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Callable

from .config import Config
from .telegram import split_text

log = logging.getLogger("announcer")

Engine = Callable[[str, Path], None]  # (text, mp3_path) -> writes the file

PCM_RATE, PCM_WIDTH, PCM_CHANNELS = 24_000, 2, 1   # Gemini TTS: 24 kHz, 16-bit, mono
TTS_CHUNK = 1_500


class VoiceError(RuntimeError):
    pass


def to_mp3(wav: Path, out: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise VoiceError("ffmpeg not found")
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "4", str(out)],
        check=True, capture_output=True, timeout=300,
    )


def pcm_frames(audio: bytes | str) -> bytes:
    """Raw PCM frames from Gemini's audio, which may be base64, a WAV file, or bare PCM."""
    raw = base64.b64decode(audio) if isinstance(audio, str) else audio
    if raw[:4] == b"RIFF":
        with wave.open(io.BytesIO(raw)) as wf:
            return wf.readframes(wf.getnframes())
    return raw


def write_wav(path: Path, frames: list[bytes]) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(PCM_CHANNELS)
        wf.setsampwidth(PCM_WIDTH)
        wf.setframerate(PCM_RATE)
        silence = b"\x00" * int(PCM_RATE * PCM_WIDTH * 0.4)   # short pause between chunks
        wf.writeframes(silence.join(frames))


def gemini_tts_engine(api_key: str, model: str, voice: str, style: str, synth=None) -> Engine:
    """synth(text) -> audio is injectable for tests; by default it calls the Interactions API."""

    def default_synth(text: str):
        from google import genai
        from google.genai import errors, types

        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=180_000))
        for attempt in range(3):
            try:
                interaction = client.interactions.create(
                    model=model,
                    input=[{
                        "type": "user_input",
                        "content": [{
                            "type": "text",
                            "text": text,
                            "annotations": [{"type": "speech_metadata", "style": style}],
                        }],
                    }],
                    response_format={"type": "audio"},
                    generation_config={"speech_config": [{"voice": voice}]},
                )
                return interaction.output_audio.data
            except errors.ServerError:
                if attempt == 2:
                    raise
                log.warning("gemini-tts server error, retrying attempt=%d", attempt + 2)
                time.sleep(5 * (attempt + 1))

    def run(text: str, out: Path) -> None:
        make = synth or default_synth
        frames = [pcm_frames(make(chunk)) for chunk in split_text(text, TTS_CHUNK)]
        if not any(frames):
            raise VoiceError("gemini-tts returned no audio")
        wav = out.with_suffix(".wav")
        write_wav(wav, frames)
        to_mp3(wav, out)
        wav.unlink(missing_ok=True)

    return run


def edge_engine(voice: str, rate: str = "+0%") -> Engine:
    def run(text: str, out: Path) -> None:
        import edge_tts

        asyncio.run(edge_tts.Communicate(text, voice, rate=rate).save(str(out)))

    return run


def piper_engine(voice: str, voice_dir: str, rate: str = "+0%") -> Engine:
    def run(text: str, out: Path) -> None:
        from piper import PiperVoice, SynthesisConfig

        model = Path(voice_dir) / f"{voice}.onnx"
        if not model.exists():
            os.makedirs(voice_dir, exist_ok=True)
            subprocess.run(
                [sys.executable, "-m", "piper.download_voices", "--download-dir", voice_dir, voice],
                check=True, capture_output=True, timeout=300,
            )
        wav = out.with_suffix(".wav")
        with wave.open(str(wav), "wb") as wf:
            # Piper's length_scale is duration: -15% speed -> ~1.18x longer.
            speed = 1 + int(rate.rstrip("%")) / 100
            PiperVoice.load(str(model)).synthesize_wav(text, wf, syn_config=SynthesisConfig(length_scale=1 / speed))
        to_mp3(wav, out)
        wav.unlink(missing_ok=True)

    return run


def synthesize(text: str, out: Path, engines: list[tuple[str, Engine]]) -> str:
    """Try each engine in order; return the name of the one that produced audio."""
    for name, engine in engines:
        try:
            out.unlink(missing_ok=True)
            engine(text, out)
            if out.exists() and out.stat().st_size > 0:
                return name
            log.warning("tts engine=%s produced no audio", name)
        except Exception as exc:
            log.warning("tts engine=%s failed type=%s", name, type(exc).__name__)
    raise VoiceError("every voice engine failed")


def default_engines(cfg: Config, gender: str | None) -> list[tuple[str, Engine]]:
    g = gender or cfg.default_gender()
    engines: list[tuple[str, Engine]] = []
    if cfg.gemini_api_key and cfg.gemini_tts_model:
        engines.append(("gemini-tts", gemini_tts_engine(
            cfg.gemini_api_key, cfg.gemini_tts_model, cfg.gemini_tts_voices[g], cfg.tts_style)))
    engines.append(("edge-tts", edge_engine(cfg.edge_voice(gender), cfg.voice_rate)))
    engines.append(("piper", piper_engine(cfg.piper_voices[g], cfg.piper_dir, cfg.voice_rate)))
    return engines
