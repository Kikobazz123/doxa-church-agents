"""tts-preprocess.md: clean-up, tables, abbreviations, numbers, names, display vs spoken."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from announcer import script, voice
from announcer.config import GEMINI_TTS_VOICES
from announcer.normalise import normalise
from announcer.speech import load_lexicon, respell, to_speech

TABLE = """\
| S/N | CENTRE | ATT | S/N | CENTRE | ATT |
|---|---|---|---|---|---|
| 1 | BONNY STREET | 19 | 7 | | |
| 2 | MACCOBA | 14 | 8 | | |
| 3 | GOLF ESTATE 2 | 10 | 9 | | |
| 4 | NEW ROAD | 5 | 10 | | |
| 5 | NTA ROAD | 4 | 11 | | |
| 6 | PANAMA ESTATE | 2 | 12 | | |"""

TABLE_SENTENCES = (
    "The attendance by centre is as follows. First, Bonny Street, 19 in attendance. "
    "Second, Maccoba, 14 in attendance. Third, Golf Estate 2, 10 in attendance. "
    "Fourth, New Road, 5 in attendance. Fifth, NTA Road, 4 in attendance. "
    "Sixth, Panama Estate, 2 in attendance."
)


# -- §1 clean-up ---------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("A****NNOUNCEMENTS", "Announcements."),
    ("**CELL PRAYER REPORT**", "Cell Prayer Report."),
    ("DOXA FAMILY CHURCH", "Doxa Family Church."),
    ("WELCOME TO DOXA:", "Welcome to Doxa."),
    ("Thanks to all DOXA members", "Thanks to all Doxa members"),
    ("- Choir practice holds on Saturday", "Choir practice holds on Saturday"),
    ("Youth meeting | after service", "Youth meeting after service"),
])
def test_clean_up(raw, expected):
    assert normalise(raw) == expected


def test_rules_and_page_numbers_are_removed():
    assert normalise("Choir practice holds on Saturday.\n---\n2\nPage 3\nANNOUNCEMENTS 4") == \
        "Choir practice holds on Saturday.\nAnnouncements."


# -- §2 tables ------------------------------------------------------------------

def test_side_by_side_table_becomes_sentences():
    assert normalise(TABLE) == TABLE_SENTENCES


def test_table_rows_merge_in_serial_order_across_groups():
    table = "| S/N | CENTRE | ATT | S/N | CENTRE | ATT |\n| 1 | A STREET | 3 | 3 | C ROAD | 7 |\n| 2 | B LANE | 4 | | | |"
    assert normalise(table) == ("The attendance by centre is as follows. First, A Street, 3 in attendance. "
                                "Second, B Lane, 4 in attendance. Third, C Road, 7 in attendance.")


def test_total_rows_become_their_own_sentences():
    table = "| S/N | CENTRE | ATT |\n| 1 | BONNY STREET | 19 |\n| | TOTAL ATTENDANCE FOR LAST WEEK | 54 |"
    assert normalise(table).endswith("The total attendance for last week was 54.")


def test_table_speech_matches_the_md_example():
    spoken, used = to_speech(normalise(TABLE), lexicon={})
    assert spoken == (
        "The attendance by centre is as follows. First, Bonny Street, nineteen in attendance. "
        "Second, Maccoba, fourteen in attendance. Third, Golf Estate two, ten in attendance. "
        "Fourth, New Road, five in attendance. Fifth, N. T. A. Road, four in attendance. "
        "Sixth, Panama Estate, two in attendance."
    )


# -- §3 abbreviations, symbols, numbers --------------------------------------------

@pytest.mark.parametrize("display,spoken", [
    ("Ps. Ade will minister", "Pastor Ade will minister."),
    ("Ps Ade will minister", "Pastor Ade will minister."),
    ("Rev. John leads", "Reverend John leads."),
    ("Dr. Ade speaks", "Doctor Ade speaks."),
    ("Mr. and Mrs Ade", "Mister and Missus Ade."),
    ("the GO will visit", "the General Overseer will visit."),
    ("RCCG youth rally", "R. C. C. G. youth rally."),
    ("Choir & ushers", "Choir and ushers."),
    ("Starts 5:30pm", "Starts five thirty p.m."),
    ("Vigil 8:00 – 11:00am", "Vigil eight to eleven a.m."),
    ("The 1st and 26th", "The first and twenty sixth."),
    ('The theme is "Rising Higher"', 'The theme is, "Rising Higher"'),
    ("Call 08031234567", "Call 08031234567."),
    ("Read John 3:16", "Read John 3:16."),
    ("Levy is ₦5,000", "Levy is five thousand naira."),
])
def test_abbreviations_and_numbers(display, spoken):
    assert to_speech(display, lexicon={})[0] == spoken


# -- §4 names -------------------------------------------------------------------

SEED = json.loads((Path(__file__).resolve().parents[1] / "pronunciations.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,expected", list(SEED.items()) + [
    ("Nwachukwu", "Nwah-choo-kwoo"),
    ("Ya'u", "Yah-oo"),
    ("Gbenga", "Gben-gah"),
    ("Ṣẹgun", "Sheh-gun"),
])
def test_rules_reproduce_the_seed_lexicon(name, expected):
    assert respell(name) == expected


@pytest.mark.parametrize("name", ["Grace", "James", "Jones", "Strauss", "Xavier"])
def test_english_or_unsure_names_are_left_alone(name):
    assert respell(name) is None


def test_lexicon_wins_and_substitutions_are_reported():
    spoken, used = to_speech("Pastor Eke thanks Brother Chidi.", ["Chidi"], lexicon={"eke": "Eh-kay"})
    assert spoken == "Pastor Eh-kay thanks Brother Chee-dee."
    assert used == {"Eke": "Eh-kay", "Chidi": "Chee-dee"}


def test_unflagged_names_are_not_respelled():
    assert to_speech("Brother Chidi and Sister Grace.", [], lexicon={})[0] == "Brother Chidi and Sister Grace."


def test_seed_lexicon_loads():
    assert load_lexicon()["abuloma"] == "Ah-boo-loh-mah"


# -- display vs spoken, Gemini JSON, fact guard -------------------------------------

def test_display_keeps_digits_and_names_while_spoken_is_respelled(cfg):
    raw = "CELL PRAYER REPORT\nPs. Tonte thanks everyone at Abuloma. Levy is ₦5,000."
    reply = json.dumps({"script": "Good morning. Ps. Tonte thanks everyone at Abuloma. Levy is ₦5,000.",
                        "nigerian_names": ["Tonte", "Abuloma"]})
    result = script.build(raw, cfg, generate=lambda s, u: reply)
    assert result.source == "gemini"
    assert "Tonte" in result.display and "₦5,000" in result.display and "Ton-teh" not in result.display
    assert "Pastor Ton-teh" in result.spoken and "Ah-boo-loh-mah" in result.spoken
    assert "five thousand naira" in result.spoken
    assert result.pronounced == {"Tonte": "Ton-teh", "Abuloma": "Ah-boo-loh-mah"}


def test_guard_ignores_reworded_headings(cfg):
    raw = "CELL PRAYER REPORT\nBible study holds on Wednesday at Maccoba."
    reply = json.dumps({"script": "Good morning. Bible study holds on Wednesday at Maccoba.", "nigerian_names": []})
    assert script.build(raw, cfg, generate=lambda s, u: reply).source == "gemini"


def test_table_survives_the_guard(cfg):
    original = normalise(TABLE)
    reply = json.dumps({"script": "Good morning, church. " + original + " God bless you.", "nigerian_names": ["Maccoba"]})
    result = script.build(TABLE, cfg, generate=lambda s, u: reply)
    assert result.source == "gemini" and "|" not in result.display and "|" not in result.spoken


def test_plain_text_reply_is_still_accepted():
    assert script.parse_reply("Just a script.") == ("Just a script.", [])
    assert script.parse_reply('{"script": "S", "nigerian_names": ["Eke", 3]}') == ("S", ["Eke"])


# -- Gemini TTS --------------------------------------------------------------------

def _pcm(seconds=0.2):
    return b"\x01\x00" * int(voice.PCM_RATE * seconds)


def test_gemini_tts_joins_chunks_into_one_mp3(tmp_path):
    calls = []

    def synth(text):
        calls.append(text)
        return _pcm()

    engine = voice.gemini_tts_engine("k", "m", "Kore", "style", synth=synth)
    long_text = "\n\n".join(["Paragraph number one is here. " * 20] * (voice.TTS_CHUNK // 300 + 2))
    out = tmp_path / "a.mp3"
    engine(long_text, out)
    assert len(calls) > 1 and all(len(c) <= voice.TTS_CHUNK for c in calls)
    assert out.exists() and out.stat().st_size > 0


def test_pcm_frames_accepts_base64_and_wav():
    import base64
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000); wf.writeframes(_pcm())
    assert voice.pcm_frames(buf.getvalue()) == _pcm()
    assert voice.pcm_frames(base64.b64encode(_pcm()).decode()) == _pcm()


def test_engine_order_gemini_then_edge_then_piper(cfg):
    names = [n for n, _ in voice.default_engines(replace(cfg, gemini_tts_model="gemini-tts-model"), "male")]
    assert names == ["gemini-tts", "edge-tts", "piper"]
    assert [n for n, _ in voice.default_engines(cfg, None)] == ["edge-tts", "piper"]
    female_off = replace(cfg, gemini_tts_model="m", gemini_tts_voices={"female": "off", "male": "Charon"})
    assert [n for n, _ in voice.default_engines(female_off, "female")] == ["edge-tts", "piper"]
    assert [n for n, _ in voice.default_engines(female_off, "male")][0] == "gemini-tts"
    assert GEMINI_TTS_VOICES["male"]


def test_gemini_falls_back_to_second_model_on_server_errors(cfg, monkeypatch):
    from google import genai
    from google.genai import errors

    tried = []

    class FakeModels:
        def generate_content(self, model, contents, config):
            tried.append(model)
            if model == "main":
                raise errors.ServerError(500, {"error": {"code": 500, "status": "INTERNAL", "message": "Internal error"}})
            return type("R", (), {"text": '{"script": "ok", "nigerian_names": []}'})()

    monkeypatch.setattr(genai, "Client", lambda **kw: type("C", (), {"models": FakeModels()})())
    monkeypatch.setattr(script.time, "sleep", lambda s: None)
    generate = script.gemini_generate(replace(cfg, gemini_model="main", gemini_fallback_models=("backup",)))
    assert script.parse_reply(generate("sys", "user")) == ("ok", [])
    assert tried == ["main", "main", "backup"]


def test_gemini_client_error_is_not_retried(cfg, monkeypatch):
    from google import genai
    from google.genai import errors

    tried = []

    class FakeModels:
        def generate_content(self, model, contents, config):
            tried.append(model)
            raise errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota"}})

    monkeypatch.setattr(genai, "Client", lambda **kw: type("C", (), {"models": FakeModels()})())
    generate = script.gemini_generate(replace(cfg, gemini_model="main", gemini_fallback_models=("backup",)))
    with pytest.raises(errors.ClientError):
        generate("sys", "user")
    assert tried == ["main"]
