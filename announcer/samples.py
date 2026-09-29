"""Render the same short announcement in several voices, to choose one by ear.

    python -m announcer.samples            # writes voice-samples/*.mp3

Run from the workflow with "voice_samples" ticked, so it uses the repo's Gemini
key; the MP3s come back as a downloadable artifact. The sample text is fixed
and contains no real announcement.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from . import config, voice
from .normalise import normalise
from .speech import to_speech

log = logging.getLogger("announcer")

SAMPLE = """GOOD MORNING DOXA FAMILY CHURCH
Welcome to the house of God. Ps. Tonte and Mr. and Mrs Eke thank everyone who came for the vigil on the 26th, 8:00 – 11:00pm.
The harvest thanksgiving levy is ₦5,000 per family. Please pay to Deacon Barisua before Sunday.
| S/N | CENTRE | ATT |
|---|---|---|
| 1 | BONNY STREET | 19 |
| 2 | ABULOMA | 14 |
| 3 | NTA ROAD | 4 |
God bless you."""

DEFAULT_GEMINI_VOICES = "Sulafat,Kore,Achernar,Charon,Achird,Orus"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("httpx", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    key, model = os.environ.get("GEMINI_API_KEY", ""), os.environ.get("GEMINI_TTS_MODEL", "")
    style = os.environ.get("TTS_STYLE") or config.DEFAULT_TTS_STYLE
    out_dir = Path("voice-samples")
    out_dir.mkdir(exist_ok=True)

    spoken, _ = to_speech(normalise(SAMPLE), ["Tonte", "Eke", "Barisua", "Abuloma"])
    (out_dir / "spoken-text.txt").write_text(spoken, encoding="utf-8")
    log.info("spoken text:\n%s", spoken)

    made = 0
    if key and model:
        for i, name in enumerate(v.strip() for v in (os.environ.get("SAMPLE_VOICES") or DEFAULT_GEMINI_VOICES).split(",")):
            if i:
                time.sleep(25)     # stay under the free tier's requests-per-minute limit
            out = out_dir / f"gemini-{name}.mp3"
            try:
                voice.gemini_tts_engine(key, model, name, style)(spoken, out)
                log.info("sample voice=gemini-%s ok bytes=%d", name, out.stat().st_size)
                made += 1
            except Exception as exc:
                log.error("sample voice=gemini-%s failed %s: %s", name, type(exc).__name__, str(exc)[:300])
    else:
        log.error("GEMINI_API_KEY or GEMINI_TTS_MODEL not set; skipping Gemini voices")

    for name in ("en-GB-SoniaNeural", "en-GB-RyanNeural"):
        out = out_dir / f"edge-{name}.mp3"
        try:
            voice.edge_engine(name, "-15%")(spoken, out)
            log.info("sample voice=edge-%s ok", name)
        except Exception as exc:
            log.error("sample voice=edge-%s failed %s", name, type(exc).__name__)
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
