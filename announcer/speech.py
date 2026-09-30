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
from functools import lru_cache
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

DATA_DIR = Path(__file__).resolve().parent / "data"
COMMON_RANK = 40_000          # the top 40,000 English words are never respelled
_TOKEN = re.compile(r"[^\W\d_][\w'’]*")
_ENGLISH_LETTERS = re.compile(r"th|ph|wh|ck|ght|tion|sion|[xq]")
_ENGLISH_ENDINGS = (
    "ory", "ology", "ness", "ment", "ing", "ers", "ful", "less", "ity", "ism", "ist", "ance", "ence",
    "ship", "able", "ible", "ive", "ous", "ary", "ery", "ly", "ed", "age", "ture",
)


@lru_cache(maxsize=1)
def english_rank() -> dict[str, int]:
    """Word -> frequency rank (0 = most common), from announcer/data/english_words.txt."""
    try:
        words = (DATA_DIR / "english_words.txt").read_text(encoding="utf-8").split()
    except OSError:
        return {}
    return {w: i for i, w in enumerate(words)}


@lru_cache(maxsize=1)
def keep_as_written() -> frozenset[str]:
    """ENGLISH_SAFE plus announcer/data/keep_as_written.txt (Bible books, names, places, church words)."""
    try:
        extra = [l.strip().lower() for l in (DATA_DIR / "keep_as_written.txt").read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.lstrip().startswith("#")]
    except OSError:
        extra = []
    return frozenset(ENGLISH_SAFE | set(extra))


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


def _respell_part(part: str, strict: bool) -> str | None:
    w = _letters(part)
    if not w or not w.isalpha():
        return None
    w = re.sub(r"([bcdfghjklmnprstvwz])\1", r"\1", w)       # Maccoba -> Macoba
    w = re.sub(r"([aeiou])\1", r"\1", w)                      # Dinee -> Dine
    units = _units(w)
    if not units:
        return None

    syllables: list[list[str]] = []    # [onset, vowel, coda]; a lone nasal has vowel ""
    onset: list[str] = []
    i = 0
    while i < len(units):
        u = units[i]
        if u not in _VOWELS:
            onset.append(u); i += 1
            continue
        # A lone h before another consonant is silent (Oahre -> Oh-ah-reh).
        onset = [c for j, c in enumerate(onset) if not (c == "h" and j < len(onset) - 1)]
        if len(onset) > 1 and onset[0] in ("m", "n") and not syllables:
            syllables.append(["", "", onset[0]]); onset = onset[1:]   # syllabic nasal: Mbakwe -> m-bah-kweh
        if len(onset) == 2:
            if not strict and onset[1] in ("r", "l", "w", "y"):
                pass                                   # Ibrahim -> Ee-brah-him
            elif not strict and syllables and syllables[-1][1] and not syllables[-1][2]:
                syllables[-1][2] = onset.pop(0)        # Abdullahi -> Ab-doo-lah-hee
            else:
                return None
        elif len(onset) > 2:
            return None                                # three consonants: unsure
        nxt = units[i + 1] if i + 1 < len(units) else None
        after = units[i + 2] if i + 2 < len(units) else None
        if nxt in ("n", "m") and (after is None or after not in _VOWELS):
            syllables.append(["".join(onset), u, nxt]); i += 2      # coda: Ton-teh
        else:
            syllables.append(["".join(onset), u, ""]); i += 1
        onset = []
    if onset:
        if strict or len(onset) > 1 or not syllables or syllables[-1][2] or not syllables[-1][1]:
            return None                                # trailing consonants: unsure
        syllables[-1][2] = onset[0]                    # Okafor -> Oh-kah-for
    return "-".join(
        coda if not vowel else onset_ + (_PLAIN.get(vowel, vowel) + coda if coda else _VOWELS[vowel])
        for onset_, vowel, coda in syllables
    )


def looks_english(word: str) -> bool:
    w = word.lower()
    return bool(_ENGLISH_LETTERS.search(w)) or w.endswith(_ENGLISH_ENDINGS)


def respell(name: str, strict: bool = False) -> str | None:
    """Rule-based respelling of a Nigerian word, or None when the rules aren't sure.

    strict: only vowel / n / m syllable endings and no clusters, for words that
    could be rare English. Otherwise final consonants and simple clusters are allowed.
    """
    if name.lower() in keep_as_written() or looks_english(name):
        return None
    parts = [_respell_part(p, strict) for p in re.split(r"['’]", name) if p]
    if not parts or any(p is None for p in parts):
        return None
    spelled = "-".join(parts)
    return spelled[:1].upper() + spelled[1:]


def spoken_form(word: str, lexicon: dict[str, str], flagged: set[str] = frozenset()) -> str | None:
    """How one word should be said, or None to leave it as written."""
    low = word.lower()
    if low in lexicon:
        return lexicon[low]
    if len(word) < 3 or word.isupper() or low in keep_as_written():
        return None
    if low in flagged:
        return respell(word)
    rank = english_rank().get(low)
    if rank is not None and rank < COMMON_RANK:
        return None                                    # everyday English, and well-known names like Lagos
    # Capitalised (a name or place): extended rules. Lower case: strict, so rare English survives.
    spelled = respell(word, strict=not word[0].isupper())
    if spelled and word[0].islower():
        spelled = spelled.lower()
    return spelled


def respell_words(text: str, flagged: list[str], lexicon: dict[str, str]) -> tuple[str, dict[str, str]]:
    """Respell every Nigerian word in the text, found in code; Gemini's list only adds to it."""
    flagged_set = {w.lower() for name in flagged for w in _TOKEN.findall(name)}
    decided: dict[str, str | None] = {}
    used: dict[str, str] = {}

    def repl(m: re.Match) -> str:
        word = m.group(0)
        low = word.lower()
        if low not in decided:
            decided[low] = spoken_form(word, lexicon, flagged_set)
        spoken = decided[low]
        if not spoken:
            return word
        used.setdefault(word[:1].upper() + word[1:], spoken)
        return spoken

    return _TOKEN.sub(repl, text), used

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
    text, used = respell_words(text, nigerian_names or [], load_lexicon() if lexicon is None else lexicon)
    return final_check(text), used
