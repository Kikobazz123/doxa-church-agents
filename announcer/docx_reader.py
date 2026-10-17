"""Read the text of a Word .docx file, paragraphs and tables in document order.

A .docx is a zip with the body in word/document.xml, so the standard library is
enough. Tables come out as "| a | b |" rows, which normalise.py already turns
into spoken sentences. Headers and footers (page numbers) are skipped.
"""

from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_BYTES = 20 * 1024 * 1024        # Telegram bots can't download more than this anyway


class DocxError(ValueError):
    pass


def _paragraph_text(p: ET.Element) -> str:
    parts = []
    for el in p.iter():
        if el.tag == f"{W}t" and el.text:
            parts.append(el.text)
        elif el.tag == f"{W}tab":
            parts.append(" ")
        elif el.tag in (f"{W}br", f"{W}cr"):
            parts.append("\n")
    return "".join(parts).strip()


def _cell_text(tc: ET.Element) -> str:
    return " ".join(t for t in (_paragraph_text(p) for p in tc.findall(f"{W}p")) if t).replace("|", "/")


def _table_lines(tbl: ET.Element) -> list[str]:
    lines = []
    for tr in tbl.findall(f"{W}tr"):
        cells = []
        for tc in tr.findall(f"{W}tc"):
            span = tc.find(f"{W}tcPr/{W}gridSpan")
            cells.append(_cell_text(tc))
            cells.extend([""] * (int(span.get(f"{W}val", "1")) - 1 if span is not None else 0))
        if any(cells):
            lines.append("| " + " | ".join(cells) + " |")
    return lines


def docx_to_text(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise DocxError("file too large")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ET.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise DocxError("not a readable .docx file") from exc

    body = root.find(f"{W}body")
    if body is None:
        raise DocxError("document has no body")
    blocks: list[str] = []
    for child in body:
        if child.tag == f"{W}p":
            blocks.append(_paragraph_text(child))
        elif child.tag == f"{W}tbl":
            blocks.append("\n".join(_table_lines(child)))
        elif child.tag == f"{W}sdt":                      # content controls wrap ordinary paragraphs
            blocks.extend(_paragraph_text(p) for p in child.iter(f"{W}p"))
    text = "\n".join(blocks)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()
