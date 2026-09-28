import re
from pathlib import Path

import pytest

from announcer import script, voice
from announcer.numbers import speakable

INPUT = (
    "Choir rehearsal holds on Saturday 4th October at 4pm in the Main Auditorium.\n"
    "Harvest thanksgiving levy is ₦5,000 per family. Pay to Deacon Obi.\n"
    "Youth outreach to Ikeja on Sunday after 2nd service."
)


@pytest.mark.parametrize("text,expected", [
    ("Levy is ₦5,000 per family", "Levy is five thousand naira per family"),
    ("Pay N2,500.50 today", "Pay two thousand five hundred naira fifty kobo today"),
    ("Dues #10,000", "Dues ten thousand naira"),
    ("Target ₦2.5m", "Target two million five hundred thousand naira"),
    ("Bring 1,000 naira", "Bring one thousand naira"),
    ("Starts 9:00am sharp", "Starts nine a.m. sharp"),
    ("Ends 4:30 PM", "Ends four thirty p.m."),
    ("Doors open 7:05am", "Doors open seven oh five a.m."),
    ("Call 08031234567", "Call 08031234567"),
    ("amazing 5 amazing", "amazing 5 amazing"),
])
def test_speakable(text, expected):
    assert speakable(text) == expected


def test_gemini_script_is_used_when_facts_survive(cfg):
    draft = "Good morning, Doxa Family Church. " + INPUT.replace("\n", " ") + " God bless you."
    result = script.build(INPUT, cfg, generate=lambda s, u: draft)
    assert result.source == "gemini" and result.note is None
    assert "five thousand naira" in result.text and "four p.m." in result.text


def test_fact_guard_rejects_changed_amount(cfg):
    draft = INPUT.replace("₦5,000", "₦50,000")
    result = script.build(INPUT, cfg, generate=lambda s, u: draft)
    assert result.source == "original" and "5000" in result.note


def test_fact_guard_rejects_dropped_name(cfg):
    draft = INPUT.replace("Deacon Obi", "the deacon")
    result = script.build(INPUT, cfg, generate=lambda s, u: draft)
    assert result.source == "original" and "Obi" in result.note


def test_gemini_failure_voices_original_text(cfg):
    def down(s, u):
        raise ConnectionError("quota")

    result = script.build(INPUT, cfg, generate=down)
    assert result.source == "original"
    assert result.text == speakable(script.clean(INPUT))


def test_prompt_carries_church_name_and_rules(cfg):
    seen = {}

    def capture(system, user):
        seen["system"], seen["user"] = system, user
        return INPUT

    script.build(INPUT, cfg, generate=capture)
    assert "Doxa Family Church" in seen["system"] and "Never add or invent" in seen["system"]
    assert seen["user"].startswith("<announcements>")


def test_church_name_is_optional(cfg, monkeypatch):
    from dataclasses import replace

    from announcer import config

    seen = {}
    script.build(INPUT, replace(cfg, church_name=""), generate=lambda s, u: seen.setdefault("system", s) and INPUT)
    assert "Doxa" not in seen["system"] and "does not name any church" in seen["system"]

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "-5103583597")
    monkeypatch.delenv("CHURCH_NAME", raising=False)
    monkeypatch.delenv("VOICE", raising=False)
    loaded = config.load()
    assert loaded.church_name == "" and loaded.label == "Church"
    assert loaded.edge_voice(None) == "en-NG-EzinneNeural" and loaded.edge_voice("male") == "en-NG-AbeoNeural"


def test_voice_and_speed_come_from_variables(monkeypatch):
    from announcer import config

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    monkeypatch.setenv("VOICE_FEMALE", "en-US-AvaNeural")
    monkeypatch.setenv("VOICE_MALE", "en-US-AndrewNeural")
    monkeypatch.delenv("VOICE", raising=False)
    monkeypatch.delenv("VOICE_RATE", raising=False)
    c = config.load()
    assert c.edge_voice(None) == "en-US-AvaNeural" and c.edge_voice("male") == "en-US-AndrewNeural"
    assert c.voice_rate == "-15%"

    monkeypatch.setenv("VOICE_RATE", "slow")
    with pytest.raises(config.ConfigError):
        config.load()


def test_clean_strips_emoji_and_markdown():
    assert script.clean("## Notice 🎉\n- **Bible study** on *Wednesday*") == "Notice\nBible study on Wednesday"


def test_sentence_start_words_are_not_required():
    numbers, names = script.facts("Please note. Bible study holds on Wednesday with Pastor Ade.")
    assert names == {"Wednesday", "Pastor", "Ade"}


def test_voice_falls_back_to_piper(tmp_path: Path):
    def edge(text, out):
        raise ConnectionError("blocked")

    def piper(text, out):
        out.write_bytes(b"mp3")

    assert voice.synthesize("hi", tmp_path / "a.mp3", [("edge-tts", edge), ("piper", piper)]) == "piper"


def test_voice_raises_when_all_fail(tmp_path: Path):
    def empty(text, out):
        out.write_bytes(b"")

    with pytest.raises(voice.VoiceError):
        voice.synthesize("hi", tmp_path / "a.mp3", [("edge-tts", empty)])


def test_workflow_schedule_matches_spec():
    wf = (Path(__file__).resolve().parents[1] / ".github/workflows/announcer.yml").read_text(encoding="utf-8")
    assert re.search(r"^name: Church Announcer$", wf, re.M)
    for cron in ("*/20 * * * 5,6", "*/20 0-4,8-23 * * 0", "*/5 5-7 * * 0", "0 */12 * * 1-4"):
        assert f"cron: '{cron}'" in wf
    assert "workflow_dispatch" in wf and "group: announcer" in wf
