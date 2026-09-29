import pytest
from conftest import (BOT_ID, GROUP, PRIVATE, STRANGER, EngineSpy, FakeTelegram,
                      fake_script, make_update)

from announcer.main import Announcer, deadline_today, parse_command, run
from announcer.telegram import TelegramError, split_text

LONG = "Choir rehearsal holds on Saturday at 4pm in the main auditorium."


def one_run(tg, cfg, engines=None):
    announcer = Announcer(cfg, tg, build_script=fake_script, engines_for=engines or EngineSpy())
    run(tg, announcer)
    return announcer


def test_announcement_gets_script_and_mp3(cfg):
    tg = FakeTelegram([make_update(1, LONG)])
    one_run(tg, cfg)
    assert tg.messages == [(PRIVATE, f"SCRIPT: {LONG}")]
    assert len(tg.audio) == 1 and tg.audio[0][1].endswith(".mp3")


def test_second_run_sends_nothing(cfg):
    tg = FakeTelegram([make_update(1, LONG), make_update(2, LONG)])
    one_run(tg, cfg)
    sent = (len(tg.messages), len(tg.audio))
    one_run(tg, cfg)
    assert (len(tg.messages), len(tg.audio)) == sent == (2, 2)


def test_other_chats_are_ignored_and_confirmed(cfg):
    tg = FakeTelegram([make_update(1, LONG, chat_id=STRANGER)])
    a = one_run(tg, cfg)
    assert tg.messages == [] and tg.audio == [] and tg.queue == []
    assert a.stats["ignored_chat"] == 1


@pytest.mark.parametrize("text,reply_from,expected", [
    ("Amen, thank you", None, "ignored_chatter"),
    (LONG, None, "announced"),
    (LONG, 42, "ignored_chatter"),                       # reply to another member
    ("Service at 8am", BOT_ID, "announced"),             # reply to the bot
    ("@DoxaAnnouncerBot Service at 8am", None, "announced"),
])
def test_group_filters_everyday_chat(cfg, text, reply_from, expected):
    tg = FakeTelegram([make_update(1, text, chat_id=GROUP, chat_type="supergroup", reply_to_from=reply_from)])
    a = one_run(tg, cfg)
    assert a.stats[expected] == 1


def test_mention_is_removed_from_announcement(cfg):
    tg = FakeTelegram([make_update(1, "@DoxaAnnouncerBot Service at 8am", chat_id=GROUP, chat_type="group")])
    one_run(tg, cfg)
    assert tg.messages[0][1] == "SCRIPT: Service at 8am"


def test_parse_command():
    assert parse_command("/preview@DoxaAnnouncerBot hello\nworld", "doxaannouncerbot") == ("preview", "hello\nworld")
    assert parse_command("/help@SomeOtherBot", "DoxaAnnouncerBot") == ("other", "")
    assert parse_command("plain text", "DoxaAnnouncerBot") == (None, "plain text")


def test_preview_sends_no_audio(cfg):
    tg = FakeTelegram([make_update(1, "/preview " + LONG)])
    one_run(tg, cfg)
    assert tg.messages == [(PRIVATE, f"SCRIPT: {LONG}")] and tg.audio == []


def test_voice_choice_persists_to_next_run(cfg):
    tg = FakeTelegram([make_update(1, "/voice male")])
    one_run(tg, cfg)
    assert "Voice: male" in tg.description
    tg.queue.append(make_update(2, LONG))
    spy = EngineSpy()
    one_run(tg, cfg, engines=spy)
    assert spy.genders == ["male"]


def test_help(cfg):
    tg = FakeTelegram([make_update(1, "/help")])
    one_run(tg, cfg)
    assert "/preview" in tg.messages[0][1]


def test_both_voices_failing_is_reported(cfg):
    def broken(cfg, gender):
        def fail(text, out):
            raise RuntimeError("down")
        return [("edge-tts", fail), ("piper", fail)]

    tg = FakeTelegram([make_update(1, LONG)])
    a = one_run(tg, cfg, engines=broken)
    assert a.failures == 1 and tg.audio == []
    assert "every voice engine failed" in tg.messages[-1][1]


def test_unexpected_error_is_reported_and_confirmed(cfg):
    def explode(text, cfg):
        raise ValueError("boom")

    tg = FakeTelegram([make_update(1, LONG)])
    a = Announcer(cfg, tg, build_script=explode, engines_for=EngineSpy())
    run(tg, a)
    assert a.failures == 1 and "something went wrong" in tg.messages[0][1] and tg.queue == []


def test_update_left_unconfirmed_when_nothing_can_be_sent(cfg):
    tg = FakeTelegram([make_update(1, LONG)], fail_sends=True)
    a = Announcer(cfg, tg, build_script=fake_script, engines_for=EngineSpy())
    with pytest.raises(TelegramError):
        run(tg, a)
    assert len(tg.queue) == 1


def test_edited_message_is_marked_updated(cfg):
    tg = FakeTelegram([make_update(1, LONG, edited=True)])
    one_run(tg, cfg)
    assert tg.messages[0][1].startswith("Updated script:")


def test_listen_mode_stops_at_deadline(cfg):
    tg = FakeTelegram()
    ticks = iter([0, 0, 100, 100])
    a = Announcer(cfg, tg, build_script=fake_script, engines_for=EngineSpy())
    run(tg, a, deadline=50, clock=lambda: next(ticks))


def test_deadline_today():
    from datetime import datetime, timezone
    now = datetime(2026, 9, 27, 5, 3, tzinfo=timezone.utc)
    assert deadline_today("08:00", now) == datetime(2026, 9, 27, 8, 0, tzinfo=timezone.utc).timestamp()


def test_split_text_respects_limit():
    parts = split_text(("word " * 3000).strip(), limit=4096)
    assert all(len(p) <= 4096 for p in parts) and " ".join(parts).split() == ["word"] * 3000


def test_update_dropped_when_bot_was_removed_from_chat(cfg):
    tg = FakeTelegram([make_update(1, LONG)], fail_sends=True,
                      send_error="sendMessage: 403 Forbidden: bot was kicked from the group chat")
    a = Announcer(cfg, tg, build_script=fake_script, engines_for=EngineSpy())
    run(tg, a)
    assert tg.queue == [] and a.failures == 1


def test_group_is_told_which_names_were_respelled(cfg):
    from announcer.script import Script

    def with_names(text, cfg):
        return Script("Pastor Tonte", "Pastor Ton-teh", "gemini", pronounced={"Tonte": "Ton-teh"})

    tg = FakeTelegram([make_update(1, LONG)])
    a = Announcer(cfg, tg, build_script=with_names, engines_for=EngineSpy())
    run(tg, a)
    assert tg.messages[0][1] == "Pastor Tonte"
    assert "Tonte as Ton-teh" in tg.messages[1][1] and "pronunciations.json" in tg.messages[1][1]
