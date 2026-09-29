"""Turn amounts, times, ordinals and small numbers into words so the voice reads them right.

This runs in code rather than being left to Gemini. The model is told to keep
every number exactly as written, and the fact guard checks that it did.
"""

from __future__ import annotations

import re

from num2words import num2words

_MULT = {"k": 1_000, "m": 1_000_000}

# ₦5,000 · N5000 · NGN 5,000 · #5,000 (common Nigerian shorthand) · ₦2.5k · ₦1,000.50
_CURRENCY = re.compile(
    r"(?<![\w#₦])(?:₦|NGN\s?|N|#)\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?\s?([kKmM])?(?![\w])"
)
# 5,000 naira
_NAIRA_WORD = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\s?naira)\b", re.IGNORECASE)
_CLOCK = r"(\d{1,2})(?::(\d{2}))?"
_HALF = r"\s?([ap])\.?\s?m\.?(?!\w)"
# 8:00 – 11:00am · 4-6pm · 9am to 12pm (the first am/pm, if any, is dropped from speech)
_TIME_RANGE = re.compile(
    rf"(?<![\w:]){_CLOCK}(?:\s?[ap]\.?\s?m\.?)?\s*(?:-|–|—|to)\s*{_CLOCK}{_HALF}", re.IGNORECASE
)
# 9am · 9:30am · 9 a.m. · 4:00 PM
_TIME = re.compile(rf"(?<![\w:]){_CLOCK}{_HALF}", re.IGNORECASE)
# 1st · 26th
_ORDINAL = re.compile(r"(?<![\w.,:/])(\d{1,3})(st|nd|rd|th)\b", re.IGNORECASE)
# Plain numbers under 100: not part of a phone number, date, decimal, time or verse (3:16).
_SMALL = re.compile(r"(?<![\w.,:/'’-])(\d{1,2})(?![\w:/%]|[.,]\d)")


def words(n: int) -> str:
    return num2words(n, lang="en").replace(",", "").replace("-", " ")


def _currency(m: re.Match) -> str:
    whole, frac, suffix = m.group(1).replace(",", ""), m.group(2), m.group(3)
    if suffix:
        value = float(f"{whole}.{frac}" if frac else whole) * _MULT[suffix.lower()]
        return f"{words(round(value))} naira"
    spoken = f"{words(int(whole))} naira"
    if frac and int(frac):
        kobo = int(frac.ljust(2, "0"))
        spoken += f" {words(kobo)} kobo"
    return spoken


def _clock(hour: str, minute: str | None) -> str | None:
    h = int(hour)
    if not 1 <= h <= 12 or (minute and int(minute) > 59):
        return None
    spoken = words(h)
    if minute and int(minute):
        mins = int(minute)
        spoken += f" oh {words(mins)}" if mins < 10 else f" {words(mins)}"
    return spoken


def _time(m: re.Match) -> str:
    spoken = _clock(m.group(1), m.group(2))
    return f"{spoken} {m.group(3).lower()}.m." if spoken else m.group(0)


def _time_range(m: re.Match) -> str:
    start, end = _clock(m.group(1), m.group(2)), _clock(m.group(3), m.group(4))
    if not (start and end):
        return m.group(0)
    return f"{start} to {end} {m.group(5).lower()}.m."


def speakable(text: str) -> str:
    text = _CURRENCY.sub(_currency, text)
    text = _NAIRA_WORD.sub(lambda m: words(int(m.group(1).replace(",", ""))) + m.group(2), text)
    text = _TIME_RANGE.sub(_time_range, text)
    text = _TIME.sub(_time, text)
    text = _ORDINAL.sub(lambda m: num2words(int(m.group(1)), lang="en", to="ordinal").replace("-", " "), text)
    return _SMALL.sub(lambda m: words(int(m.group(1))), text)
