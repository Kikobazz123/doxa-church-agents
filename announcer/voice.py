"""Text to MP3: edge-tts first, Piper (offline) only if edge-tts fails."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from typing import Callable

from .config import Config

log = logging.getLogger("announcer")

Engine = Callable[[str, Path], None]  # (text, mp3_path) -> writes the file


class VoiceError(RuntimeError):
    pass


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
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise VoiceError("ffmpeg not found")
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "4", str(out)],
            check=True, capture_output=True, timeout=300,
        )
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
    return [
        ("edge-tts", edge_engine(cfg.edge_voice(gender), cfg.voice_rate)),
        ("piper", piper_engine(cfg.piper_voices[g], cfg.piper_dir, cfg.voice_rate)),
    ]
