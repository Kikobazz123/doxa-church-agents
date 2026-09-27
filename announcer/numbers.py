"""Turn amounts and clock times into words so the voice reads them correctly.

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
# 9am · 9:30am · 9 a.m. · 4:00 PM
_TIME = re.compile(r"(?<![\w:])(\d{1,2})(?::(\d{2}))?\s?([ap])\.?\s?m\.?(?!\w)", re.IGNORECASE)


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


def _time(m: re.Match) -> str:
    hour, minute, half = int(m.group(1)), m.group(2), m.group(3).lower()
    if not 1 <= hour <= 12 or (minute and int(minute) > 59):
        return m.group(0)
    spoken = words(hour)
    if minute and int(minute):
        mins = int(minute)
        spoken += f" oh {words(mins)}" if mins < 10 else f" {words(mins)}"
    return f"{spoken} {half}.m."


def speakable(text: str) -> str:
    text = _CURRENCY.sub(_currency, text)
    text = _NAIRA_WORD.sub(lambda m: words(int(m.group(1).replace(",", ""))) + m.group(2), text)
    return _TIME.sub(_time, text)
