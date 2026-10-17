"""Word .docx announcements: reading, and how the bot handles files sent to the group."""

import io
import zipfile

from conftest import GROUP, EngineSpy, FakeTelegram, fake_script

from announcer.docx_reader import DocxError, docx_to_text
from announcer.main import Announcer, run
from announcer.normalise import normalise

NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def p(text, bold=False):
    runs = "".join(f'<w:r>{"<w:rPr><w:b/></w:rPr>" if bold else ""}<w:t xml:space="preserve">{t}</w:t></w:r>'
                   for t in text.split("|"))
    return f"<w:p>{runs}</w:p>"


def tc(text, span=1):
    pr = f'<w:tcPr><w:gridSpan w:val="{span}"/></w:tcPr>' if span > 1 else ""
    return f"<w:tc>{pr}{p(text) if text else '<w:p/>'}</w:tc>"


def tbl(rows):
    return "<w:tbl>" + "".join("<w:tr>" + "".join(tc(*c) if isinstance(c, tuple) else tc(c) for c in r) + "</w:tr>"
                               for r in rows) + "</w:tbl>"


def make_docx(body: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f"<w:document {NS}><w:body>{body}<w:sectPr/></w:body></w:document>")
    return buf.getvalue()


ANNOUNCEMENT = make_docx(
    p("DOXA FAMILY CHURCH ANNOUNCEMENTS", bold=True)
    + p("Choir rehearsal holds on Saturday at |4pm| in the main auditorium.")
    + p("CELL PRAYER REPORT")
    + tbl([["S/N", "CENTRE", "ATT", "S/N", "CENTRE", "ATT"],
           ["1", "BONNY STREET", "19", "7", "", ""],
           ["2", "MACCOBA", "14", "8", "", ""]])
    + p("Harvest levy is ₦5,000 per family.")
)


def test_paragraphs_and_tables_come_out_in_order():
    text = docx_to_text(ANNOUNCEMENT)
    lines = text.split("\n")
    assert lines[0] == "DOXA FAMILY CHURCH ANNOUNCEMENTS"
    assert lines[1] == "Choir rehearsal holds on Saturday at 4pm in the main auditorium."
    assert lines[3] == "| S/N | CENTRE | ATT | S/N | CENTRE | ATT |"
    assert lines[-1] == "Harvest levy is ₦5,000 per family."


def test_docx_table_becomes_spoken_sentences():
    out = normalise(docx_to_text(ANNOUNCEMENT))
    assert "Doxa Family Church Announcements." in out
    assert "First, Bonny Street, 19 in attendance. Second, Maccoba, 14 in attendance." in out
    assert "|" not in out


def test_merged_cells_keep_columns_aligned():
    text = docx_to_text(make_docx(tbl([["S/N", "CENTRE", "ATT"], [("TOTAL", 2), "54"]])))
    assert text.split("\n")[1] == "| TOTAL |  | 54 |"


def test_bad_file_raises():
    import pytest
    with pytest.raises(DocxError):
        docx_to_text(b"not a zip")


# -- the bot ---------------------------------------------------------------------

class DocTelegram(FakeTelegram):
    def __init__(self, updates, files):
        super().__init__(updates)
        self.files = files

    def download_document(self, file_id):
        return self.files[file_id]


def doc_update(update_id, file_name, file_id="f1", caption=None, size=1000):
    msg = {"message_id": update_id * 10, "chat": {"id": GROUP, "type": "supergroup"},
           "from": {"id": 42, "is_bot": False},
           "document": {"file_id": file_id, "file_name": file_name, "file_size": size}}
    if caption:
        msg["caption"] = caption
    return {"update_id": update_id, "message": msg}


def bot(cfg, updates, files):
    tg = DocTelegram(updates, files)
    a = Announcer(cfg, tg, build_script=fake_script, engines_for=EngineSpy())
    run(tg, a)
    return tg, a


def test_docx_in_group_gets_script_and_mp3(cfg):
    tg, a = bot(cfg, [doc_update(1, "Sunday Announcements.docx")], {"f1": ANNOUNCEMENT})
    assert a.stats["announced"] == 1 and len(tg.audio) == 1
    assert "Choir rehearsal holds on Saturday" in tg.messages[0][1]


def test_docx_with_preview_caption_gets_script_only(cfg):
    tg, a = bot(cfg, [doc_update(1, "notes.docx", caption="/preview")], {"f1": ANNOUNCEMENT})
    assert a.stats["preview"] == 1 and tg.audio == []


def test_old_word_and_pdf_get_a_hint(cfg):
    tg, a = bot(cfg, [doc_update(1, "old.doc"), doc_update(2, "bulletin.pdf")], {})
    assert a.stats["unsupported_file"] == 2 and "save the announcements as .docx" in tg.messages[0][1]


def test_unrelated_files_are_ignored(cfg):
    tg, a = bot(cfg, [doc_update(1, "photo.jpg")], {})
    assert tg.messages == [] and a.stats["ignored_nontext"] == 1


def test_broken_or_empty_docx_is_explained(cfg):
    tg, a = bot(cfg, [doc_update(1, "a.docx", "bad"), doc_update(2, "b.docx", "empty")],
                {"bad": b"nope", "empty": make_docx("<w:p/>")})
    assert "couldn't open that Word file" in tg.messages[0][1]
    assert "looks empty" in tg.messages[1][1]


def test_docx_from_other_chats_is_ignored(cfg):
    upd = doc_update(1, "a.docx")
    upd["message"]["chat"]["id"] = 777
    tg, a = bot(cfg, [upd], {"f1": ANNOUNCEMENT})
    assert tg.messages == [] and a.stats["ignored_chat"] == 1
