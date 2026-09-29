"""Tidy a script pasted from a Word document before anything else reads it.

§1 clean-up (markdown leftovers, bullets, page numbers, ALL-CAPS headings) and
§2 tables → spoken sentences, from tts-preprocess.md. Numbers stay as digits
here so the fact guard can still check them; speech.py turns them into words.
"""

from __future__ import annotations

import re

from num2words import num2words

# Letter acronyms kept upper case, so speech.py can read them letter by letter.
ACRONYMS = {"NTA", "RCCG", "GO", "CAC", "ECWA", "NYSC", "WAEC", "JAMB", "PTA", "HQ", "UK", "USA", "FCT", "LGA", "RSU", "UPTH"}
_SMALL_WORDS = {"of", "and", "the", "for", "in", "on", "to", "a", "an", "at", "by", "with"}
_RULE = re.compile(r"^\s*([-=_*]\s*){3,}$")
_BULLET = re.compile(r"^\s*(?:[-•▪●◦·]|\d{1,2}[.)])\s+")
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s*)?-?\s*\d{1,3}\s*-?\s*$", re.I)
_TRAILING_PAGE_NUMBER = re.compile(r"(?:\t|\s{2,})\d{1,3}\s*$")
_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")


def _title_word(word: str, first: bool) -> str:
    core = re.sub(r"[^\w]", "", word)
    if core.upper() in ACRONYMS:
        return word
    if not first and word.lower() in _SMALL_WORDS:
        return word.lower()
    return word[:1].upper() + word[1:].lower()


def title_case(text: str) -> str:
    return " ".join(_title_word(w, i == 0) for i, w in enumerate(text.split()))


def _is_caps_heading(line: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", line)
    return len(letters) >= 2 and letters.isupper() and len(line.split()) <= 12 and line.strip().upper() not in ACRONYMS


def clean_line(line: str) -> str:
    line = re.sub(r"\*+|_{2,}", "", line)            # **bold**, A****NNOUNCEMENTS -> ANNOUNCEMENTS
    if _RULE.match(line) or _PAGE_NUMBER.match(line):
        return ""
    line = _TRAILING_PAGE_NUMBER.sub("", line)
    line = _BULLET.sub("", line)
    line = line.replace("|", " ")                       # stray pipes outside a table
    line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
    line = re.sub(r"\s+", " ", line).strip()
    if _is_caps_heading(line):
        line = re.sub(r"\s\d{1,3}$", "", line)          # page number stuck to a heading
        line = title_case(line).rstrip(" :;-")
        if line and line[-1] not in ".!?":
            line += "."
    return re.sub(r"\bDOXA\b", "Doxa", line)


# -- tables -------------------------------------------------------------------

def _cells(line: str) -> list[str]:
    cells = [re.sub(r"\*+", "", c).strip() for c in line.strip().split("|")]
    if line.strip().startswith("|"):
        cells = cells[1:]
    if line.strip().endswith("|"):
        cells = cells[:-1]
    return cells


def _header_key(cell: str) -> str:
    key = re.sub(r"[^A-Z/]", "", cell.upper())
    return {"SN": "S/N", "S/NO": "S/N", "NO": "S/N", "CENTER": "CENTRE", "ATTENDANCE": "ATT"}.get(key, key)


def _ordinal(n: int) -> str:
    return num2words(n, lang="en", to="ordinal").capitalize()


def _name(cell: str) -> str:
    return title_case(cell) if _is_caps_heading(cell) else cell


def table_to_sentences(lines: list[str]) -> list[str]:
    rows = [_cells(l) for l in lines]
    rows = [r for r in rows if any(r) and not all(_SEPARATOR_CELL.match(c) or not c for c in r)]
    if not rows:
        return []
    header = [_header_key(c) for c in rows[0]]
    body = rows[1:]

    # Side-by-side repeats (S/N | CENTRE | ATT | S/N | CENTRE | ATT): split into groups.
    starts = [i for i, h in enumerate(header) if h == "S/N"] or [0]
    if starts[0] != 0:
        starts = [0] + starts
    bounds = list(zip(starts, starts[1:] + [len(header)]))

    records, totals = [], []
    for g, (lo, hi) in enumerate(bounds):
        for r, row in enumerate(body):
            rec = {header[i]: (row[i] if i < len(row) else "").strip() for i in range(lo, hi)}
            label = rec.get("CENTRE", "") or next((v for k, v in rec.items() if k != "S/N" and v), "")
            if re.search(r"total|previous|last week", label, re.I):
                value = next((v for k, v in rec.items() if k not in ("S/N", "CENTRE") and v), "")
                if value:
                    totals.append(f"The {_name(label).lower().rstrip(':')} was {value}.")
                continue
            try:
                order = int(re.sub(r"\D", "", rec.get("S/N", "")) or 10_000 + g * 1_000 + r)
            except ValueError:
                order = 10_000 + g * 1_000 + r
            records.append((order, rec))
    records.sort(key=lambda x: x[0])

    sentences: list[str] = []
    if "CENTRE" in header and "ATT" in header:
        kept = [rec for _, rec in records if rec.get("CENTRE") and rec.get("ATT")]
        if kept:
            sentences.append("The attendance by centre is as follows.")
        for n, rec in enumerate(kept, 1):
            sentences.append(f"{_ordinal(n)}, {_name(rec['CENTRE'])}, {rec['ATT']} in attendance.")
    else:
        for _, rec in records:
            cells = [_name(v) for k, v in rec.items() if k != "S/N" and v]
            if cells:
                sentences.append(", ".join(cells) + ".")
    return sentences + totals


def _is_table_line(line: str) -> bool:
    return line.count("|") >= 2


def normalise(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if _is_table_line(lines[i]):
            j = i
            while j < len(lines) and _is_table_line(lines[j]):
                j += 1
            out.append(" ".join(table_to_sentences(lines[i:j])))
            i = j
            continue
        line = clean_line(lines[i])
        if line or (not lines[i].strip() and out and out[-1]):
            out.append(line)        # keep one blank line between paragraphs
        i += 1
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
