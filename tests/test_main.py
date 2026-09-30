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
    assert "Tonte as Ton-teh" in tg.messages[1][1] and "/say" in tg.messages[1][1]


# -- /say and /unsay -----------------------------------------------------------------

class FakeLexicon:
    NAME, SPELLING = None, None

    def __init__(self, tmp_path, monkeypatch, fail_push=False):
        import json
        self.path = tmp_path / "pronunciations.json"
        self.path.write_text(json.dumps({"Eke": "Eh-keh"}), encoding="utf-8")
        monkeypatch.setenv("PRONUNCIATIONS_FILE", str(self.path))
        self.pushed, self.fail_push = [], fail_push

    def set_entry(self, name, spelling):
        from announcer import lexicon_store
        return lexicon_store.set_entry(name, spelling)

    def publish(self, message):
        from announcer.lexicon_store import LexiconError
        if self.fail_push:
            raise LexiconError("push failed")
        self.pushed.append(message)


@pytest.fixture
def lexicon(tmp_path, monkeypatch):
    return FakeLexicon(tmp_path, monkeypatch)


def say(cfg, lexicon, *texts):
    tg = FakeTelegram([make_update(i + 1, t) for i, t in enumerate(texts)])
    a = Announcer(cfg, tg, build_script=fake_script, engines_for=EngineSpy(), lexicon=lexicon)
    run(tg, a)
    return tg, a


def test_say_saves_publishes_and_plays_a_sample(cfg, lexicon):
    import json
    tg, a = say(cfg, lexicon, "/say Tonte Tawn-teh")
    assert json.loads(lexicon.path.read_text(encoding="utf-8"))["Tonte"] == "Tawn-teh"
    assert lexicon.pushed == ["Pronunciation: Tonte"]
    assert "Saved. Tonte will be said as Tawn-teh" in tg.messages[0][1] and len(tg.audio) == 1


def test_saved_pronunciation_is_used_by_the_next_script(cfg, lexicon):
    from announcer.speech import to_speech
    say(cfg, lexicon, "/say Tonte Tawn-teh")
    assert to_speech("Pastor Tonte will preach.")[0] == "Pastor Tawn-teh will preach."


def test_say_name_alone_reports_current_pronunciation(cfg, lexicon):
    tg, _ = say(cfg, lexicon, "/say Eke", "/say Chidi")
    assert "Eke is said as Eh-keh (from your corrections)" in tg.messages[0][1]
    assert "Chidi is said as Chee-dee (worked out automatically)" in tg.messages[1][1]
    assert len(tg.audio) == 2


def test_say_rejects_bad_input(cfg, lexicon):
    tg, _ = say(cfg, lexicon, "/say", "/say Tonte Ton-teh!!123")
    assert "Send /say Name" in tg.messages[0][1] and "letters, hyphens" in tg.messages[1][1]
    assert lexicon.pushed == []


def test_unsay_removes_an_entry(cfg, lexicon):
    import json
    tg, _ = say(cfg, lexicon, "/unsay Eke", "/unsay Nobody")
    assert "Eke" not in json.loads(lexicon.path.read_text(encoding="utf-8"))
    assert "Removed. Eke will be worked out automatically again: Eh-keh" in tg.messages[0][1]
    assert "not in the corrections list" in tg.messages[1][1]


def test_failed_push_is_reported(cfg, tmp_path, monkeypatch):
    lex = FakeLexicon(tmp_path, monkeypatch, fail_push=True)
    tg, a = say(cfg, lex, "/say Tonte Tawn-teh")
    assert "could not save it on GitHub" in tg.messages[0][1] and a.failures == 1


def test_publish_is_a_no_op_outside_actions(tmp_path, monkeypatch):
    from announcer import lexicon_store
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    lexicon_store.publish("x")      # must not touch git