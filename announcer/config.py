"""Settings, read from the environment (GitHub Secrets / Variables in Actions)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

EDGE_VOICES = {"female": "en-NG-EzinneNeural", "male": "en-NG-AbeoNeural"}
DEFAULT_PIPER_VOICES = {"female": "en_GB-jenny_dioco-medium", "male": "en_GB-alan-medium"}
DEFAULT_TELEGRAM_API = "https://api.telegram.org"
DEFAULT_RATE = "-15%"  # a little slower than normal: clearer over a church sound system
DEFAULT_FALLBACK_MODELS = ("gemini-3.5-flash",)  # tried when the main model keeps returning 5xx
GEMINI_TTS_VOICES = {"female": "Sulafat", "male": "Charon"}
DEFAULT_TTS_STYLE = (
    "Read in a warm, clear Nigerian English accent, at a steady church-announcement pace. "
    "Pronounce Nigerian names with even syllables, every vowel sounded."
)


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    telegram_token: str
    allowed_chat_ids: frozenset[int]
    church_name: str
    gemini_api_key: str
    gemini_model: str
    default_voice: str
    edge_voices: dict[str, str]
    voice_rate: str
    piper_voices: dict[str, str]
    piper_dir: str
    telegram_api: str
    min_group_words: int
    gemini_tts_model: str = ""
    gemini_tts_voices: dict[str, str] = field(default_factory=lambda: dict(GEMINI_TTS_VOICES))
    tts_style: str = DEFAULT_TTS_STYLE
    gemini_fallback_models: tuple[str, ...] = DEFAULT_FALLBACK_MODELS

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_model)

    def edge_voice(self, gender: str | None) -> str:
        """The edge-tts voice for a /voice choice, or the configured default."""
        return self.edge_voices.get(gender or "", self.default_voice)

    @property
    def label(self) -> str:
        """Name for audio titles and the bot description; CHURCH_NAME is optional."""
        return self.church_name or "Church"

    def default_gender(self) -> str:
        return "male" if self.default_voice == self.edge_voices["male"] else "female"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load() -> Config:
    missing = [n for n in ("TELEGRAM_BOT_TOKEN", "ALLOWED_CHAT_IDS") if not _env(n)]
    if missing:
        raise ConfigError(f"Missing required settings: {', '.join(missing)}. See README > Setup.")

    try:
        chat_ids = frozenset(int(x) for x in _env("ALLOWED_CHAT_IDS").split(",") if x.strip())
    except ValueError:
        raise ConfigError("ALLOWED_CHAT_IDS must be comma-separated numbers, e.g. -1001234567890,123456789") from None
    if not chat_ids:
        raise ConfigError("ALLOWED_CHAT_IDS is empty.")

    rate = _env("VOICE_RATE") or DEFAULT_RATE
    if not re.fullmatch(r"[+-]\d{1,2}%", rate):
        raise ConfigError("VOICE_RATE must look like -15% (slower) or +10% (faster).")
    edge_voices = {
        "female": _env("VOICE_FEMALE") or EDGE_VOICES["female"],
        "male": _env("VOICE_MALE") or EDGE_VOICES["male"],
    }

    return Config(
        telegram_token=_env("TELEGRAM_BOT_TOKEN"),
        allowed_chat_ids=chat_ids,
        church_name=_env("CHURCH_NAME"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL"),
        default_voice=_env("VOICE") or edge_voices["female"],
        edge_voices=edge_voices,
        voice_rate=rate,
        piper_voices={
            "female": _env("PIPER_VOICE_FEMALE") or DEFAULT_PIPER_VOICES["female"],
            "male": _env("PIPER_VOICE_MALE") or DEFAULT_PIPER_VOICES["male"],
        },
        piper_dir=_env("PIPER_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "piper-voices"),
        telegram_api=(_env("TELEGRAM_API_BASE") or DEFAULT_TELEGRAM_API).rstrip("/"),
        min_group_words=int(_env("MIN_GROUP_WORDS") or 6),
        gemini_tts_model=_env("GEMINI_TTS_MODEL"),
        gemini_tts_voices={
            "female": _env("GEMINI_TTS_VOICE_FEMALE") or GEMINI_TTS_VOICES["female"],
            "male": _env("GEMINI_TTS_VOICE_MALE") or GEMINI_TTS_VOICES["male"],
        },
        tts_style=_env("TTS_STYLE") or DEFAULT_TTS_STYLE,
        gemini_fallback_models=tuple(m.strip() for m in _env("GEMINI_FALLBACK_MODELS").split(",") if m.strip())
        or DEFAULT_FALLBACK_MODELS,
    )
