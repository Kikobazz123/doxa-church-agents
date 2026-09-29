"""Turn the display script into the text the voice reads. Spoken text only.

§3 abbreviations and symbols, numbers (via numbers.py), §4 Nigerian name
respelling (lexicon first, then rules), and the §5 final check, from
tts-preprocess.md. Nothing here changes what is shown in Telegram.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

from .numbers import speakable

LEXICON_PATH = Path(__file__).resolve().parents[1] / "pronunciations.json"

_ABBREVIATIONS = [
    (re.compile(r"\bPs\b\.?(?=\s)"), "Pastor"),
    (re.compile(r"\bRev\.(?=\s)"), "Reverend"),
    (re.compile(r"\bDr\.(?=\s)"), "Doctor"),
    (re.compile(r"\bMrs\b\.?"), "Missus"),
    (re.compile(r"\bMr\b\.?"), "Mister"),
    (re.compile(r"\bGO\b"), "General Overseer"),
    (re.compile(r"\s*&\s*"), " and "),
]
_NOT_ACRONYMS = {"I", "II", "III", "IV", "VI", "OK", "A"}
_ACRONYM = re.compile(r"\b[A-Z]{2,5}\b")
_QUOTE_OPEN = re.compile(r"(?<=[\w)])\s+([\"“])(?=\S)")

# Names that are never respelled even if flagged: common English/Christian names
# and words that appear capitalised in announcements.
ENGLISH_SAFE = {
    "grace", "james", "john", "mary", "peter", "paul", "joy", "faith", "hope", "blessing", "esther", "ruth",
    "david", "daniel", "samuel", "joseph", "emmanuel", "victor", "favour", "mercy", "patience", "gift",
    "precious", "jones", "smith", "michael", "stephen", "philip", "timothy", "deborah", "sarah", "rebecca",
    "elizabeth", "christopher", "jonathan", "matthew", "mark", "luke", "andrew", "thomas", "simon", "juliet",
    "janet", "florence", "comfort", "charity", "godwin", "godspower", "kingsley", "christian", "promise",
    "goodluck", "innocent", "prince", "princess", "lucky", "sunday", "monday", "friday", "street", "road",
    "estate", "church", "pastor", "deacon", "deaconess", "elder", "brother", "sister", "doxa", "jesus", "god",
}

_DIGRAPHS = ("gb", "kp", "kw", "gw", "gh", "ch", "nw", "ny", "sh", "ts")
_VOWELS = {"a": "ah", "e": "eh", "i": "ee", "o": "oh", "u": "oo", "ẹ": "eh", "ọ": "aw"}
_PLAIN = {"ẹ": "e", "ọ": "aw"}
_CONSONANTS = set("bdfghjklmnprstvwyz")


def load_lexicon(path: Path | None = None) -> dict[str, str]:
    path = Path(os.environ.get("PRONUNCIATIONS_FILE") or path or LEXICON_PATH)
    try:
        return {k.lower(): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError):
        return {}


def _letters(word: str) -> str | None:
    """Lower-case, Yoruba marks resolved (ṣ→sh, ẹ, ọ kept), tone marks dropped."""
    w = unicodedata.normalize("NFD", word.lower())
    w = w.replace("ṣ", "sh").replace("ẹ", "ẹ").replace("ọ", "ọ")
    w = "".join(c for c in w if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", w)


def _units(w: str) -> list[str] | None:
    units, i = [], 0
    while i < len(w):
        if w[i:i + 2] in _DIGRAPHS:
            units.append(w[i:i + 2]); i += 2
        elif w[i] in _VOWELS:
            units.append(w[i]); i += 1
        elif w[i] == "c":
            units.append("k"); i += 1
        elif w[i] in _CONSONANTS:
            units.append(w[i]); i += 1
        else:
            return None          # x, q or anything unexpected: not sure, leave it
    return units


def _respell_part(part: str) -> str | None:
    w = _letters(part)
    if not w or not w.isalpha():
        return None
    w = re.sub(r"([bcdfghjklmnprstvwz])\1", r"\1", w)       # Maccoba -> Macoba
    w = re.sub(r"([aeiou])\1", r"\1", w)                      # Dinee -> Dine
    units = _units(w)
    if not units:
        return None

    syllables, onset, i = [], [], 0
    while i < len(units):
        u = units[i]
        if u not in _VOWELS:
            onset.append(u); i += 1
            continue
        # A lone h before another consonant is silent (Oahre -> Oh-ah-reh).
        onset = [c for j, c in enumerate(onset) if not (c == "h" and j < len(onset) - 1)]
        if len(onset) > 1:
            if onset[0] in ("m", "n"):
                syllables.append(onset[0]); onset = onset[1:]   # syllabic nasal: Mbakwe -> m-bah-kweh
            if len(onset) > 1:
                return None      # a cluster like "tr": unsure
        nxt, after = (units[i + 1] if i + 1 < len(units) else None), (units[i + 2] if i + 2 < len(units) else None)
        if nxt in ("n", "m") and (after is None or after not in _VOWELS):
            syllables.append("".join(onset) + _PLAIN.get(u, u) + nxt); i += 2      # coda: Ton-teh
        else:
            syllables.append("".join(onset) + _VOWELS[u]); i += 1
        onset = []
    if onset:
        return None              # trailing consonants that are not a coda: unsure
    return "-".join(syllables)


def respell(name: str) -> str | None:
    """Rule-based respelling of a Nigerian name, or None when the rules aren't sure."""
    if name.lower() in ENGLISH_SAFE:
        return None
    parts = [_respell_part(p) for p in re.split(r"['’]", name) if p]
    if not parts or any(p is None for p in parts):
        return None
    spelled = "-".join(parts)
    return spelled[:1].upper() + spelled[1:]


def _replace_word(text: str, word: str, spoken: str) -> tuple[str, int]:
    return re.subn(rf"(?<![\w-]){re.escape(word)}(?![\w-])", spoken, text, flags=re.IGNORECASE)


def respell_names(text: str, nigerian_names: list[str], lexicon: dict[str, str]) -> tuple[str, dict[str, str]]:
    used: dict[str, str] = {}
    for word, spoken in lexicon.items():
        text, n = _replace_word(text, word, spoken)
        if n:
            used[word.capitalize()] = spoken
    for name in nigerian_names:
        for word in re.findall(r"[^\W\d_][\w'’]*", name):
            if word.lower() in lexicon or word.capitalize() in used:
                continue
            spoken = respell(word)
            if spoken:
                text, n = _replace_word(text, word, spoken)
                if n:
                    used[word.capitalize()] = spoken
    return text, used


def final_check(text: str) -> str:
    """§5: nothing a voice would stumble on survives."""
    text = re.sub(r"[|*#]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if line and line[-1] not in ".!?,;:\"”'’)":
            line += "."
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def to_speech(display: str, nigerian_names: list[str] | None = None,
              lexicon: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    """Return (spoken text, {name: respelling used})."""
    text = display
    for pattern, spoken in _ABBREVIATIONS:
        text = pattern.sub(spoken, text)
    text = _QUOTE_OPEN.sub(r", \1", text)
    text = speakable(text)
    text = _ACRONYM.sub(lambda m: m.group(0) if m.group(0) in _NOT_ACRONYMS else ". ".join(m.group(0)) + ".", text)
    text = re.sub(r"\.\.(?=\s|$)", ".", text)
    text, used = respell_names(text, nigerian_names or [], load_lexicon() if lexicon is None else lexicon)
    return final_check(text), used
