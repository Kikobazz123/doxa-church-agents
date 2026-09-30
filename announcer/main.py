"""Poll Telegram, turn announcements into a script and MP3, reply, confirm, exit.

Stateless: confirming an update (getUpdates with a higher offset) is what stops
the next run from seeing it again, so each update is confirmed right after its
reply has gone out.

Logs hold counts and outcomes only. The repo is public, and so are its logs.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, lexicon_store, script, speech, voice
from .telegram import Telegram, TelegramError

log = logging.getLogger("announcer")

WAT = timezone(timedelta(hours=1))
USAGE = (
    "Send the week's announcements and I'll reply with a script and an MP3. "
    "/preview + text for the script only, /voice male or /voice female to change the voice, "
    "/say Name Re-spell-ing to fix how a name is said (/say Name to hear it, /unsay Name to undo)."
)
_COMMAND = re.compile(r"/(\w+)(?:@(\w+))?(?:\s+|$)(.*)", re.S)
_VOICE_SETTING = re.compile(r"voice:\s*(male|female)", re.I)
NOTE_NAMES = 15


def parse_command(text: str, bot_username: str) -> tuple[str | None, str]:
    """('help', '') for commands, (None, text) for plain text, ('other', '') for another bot's command."""
    m = _COMMAND.match(text)
    if not m:
        return None, text
    cmd, target, arg = m.group(1).lower(), m.group(2), m.group(3).strip()
    if target and target.lower() != bot_username.lower():
        return "other", ""
    return cmd, arg


class Announcer:
    def __init__(self, cfg: config.Config, tg: Telegram, build_script=script.build, engines_for=voice.default_engines,
                 lexicon=lexicon_store):
        self.cfg, self.tg = cfg, tg
        self.build_script, self.engines_for, self.lexicon = build_script, engines_for, lexicon
        me = tg.get_me()
        self.bot_id, self.username = me["id"], me.get("username", "")
        self.gender = self._stored_gender()
        self.failures = 0
        self.stats: Counter[str] = Counter()

    # -- voice setting, kept in the bot's own short description ---------------
    def _stored_gender(self) -> str | None:
        try:
            m = _VOICE_SETTING.search(self.tg.get_short_description())
        except TelegramError:
            return None
        return m.group(1).lower() if m else None

    def _set_gender(self, gender: str) -> None:
        self.tg.set_short_description(f"{self.cfg.label} announcer. Voice: {gender}")
        self.gender = gender

    # -- per update -------------------------------------------------------------
    def process(self, update: dict) -> None:
        msg = update.get("message") or update.get("edited_message")
        try:
            outcome = self.handle(msg, edited="edited_message" in update) if msg else "ignored_other"
        except Exception as exc:
            self.failures += 1
            log.error("update outcome=error type=%s", type(exc).__name__)
            try:
                self.tg.send_message(
                    msg["chat"]["id"],
                    "Sorry, something went wrong while preparing these announcements. Please send them again.",
                    msg["message_id"],
                )
            except TelegramError as send_exc:
                if " 403 " in f" {send_exc} ":
                    # Bot removed from / blocked in that chat: retrying can never succeed,
                    # and an unconfirmed update would make every later run fail on it.
                    log.error("chat unreachable (403); update dropped")
                else:
                    # Could not tell anyone. Leave it unconfirmed so the next run retries.
                    log.error("could not send the error reply; update left for the next run")
                    raise
            outcome = "error"
        self.stats[outcome] += 1
        self.tg.ack(update["update_id"])

    def handle(self, msg: dict, edited: bool = False) -> str:
        chat = msg["chat"]
        if chat["id"] not in self.cfg.allowed_chat_ids:
            return "ignored_chat"
        if msg.get("from", {}).get("is_bot"):
            return "ignored_bot"
        text = (msg.get("text") or "").strip()
        if not text:
            return "ignored_nontext"
        reply_to = msg["message_id"]

        cmd, arg = parse_command(text, self.username)
        if cmd == "other":
            return "ignored_other_bot"
        if cmd in ("help", "start"):
            self.tg.send_message(chat["id"], USAGE, reply_to)
            return "help"
        if cmd == "voice":
            return self._voice_command(chat["id"], arg.lower(), reply_to)
        if cmd in ("say", "unsay"):
            return self._say_command(chat["id"], cmd, arg, reply_to)
        if cmd == "preview":
            if not arg:
                self.tg.send_message(chat["id"], "Send /preview followed by the announcements.", reply_to)
                return "help"
            return self._announce(chat["id"], arg, reply_to, audio=False, edited=edited)
        if cmd is not None:
            self.tg.send_message(chat["id"], USAGE, reply_to)
            return "help"

        if chat.get("type") in ("group", "supergroup"):
            text = self._addressed_text(msg, text)
            if text is None:
                return "ignored_chatter"
        return self._announce(chat["id"], text, reply_to, audio=True, edited=edited)

    def _addressed_text(self, msg: dict, text: str) -> str | None:
        """In a group, only act on announcements, not on everyday chat.

        Acts on: messages that mention the bot, replies to the bot, and standalone
        messages of at least MIN_GROUP_WORDS words. Returns None to stay quiet.
        """
        mention = f"@{self.username}"
        if self.username and mention.lower() in text.lower():
            stripped = re.sub(re.escape(mention), "", text, flags=re.I).strip()
            return stripped or None
        replied = msg.get("reply_to_message")
        if replied:
            return text if replied.get("from", {}).get("id") == self.bot_id else None
        return text if len(text.split()) >= self.cfg.min_group_words else None

    def _voice_command(self, chat_id: int, arg: str, reply_to: int) -> str:
        if arg in ("male", "female"):
            self._set_gender(arg)
            self.tg.send_message(chat_id, f"Done. The {arg} voice will be used from now on.", reply_to)
            return "voice_set"
        current = self.gender or self.cfg.default_gender()
        self.tg.send_message(chat_id, f"The voice is {current}. Use /voice male or /voice female to change it.", reply_to)
        return "help"

    def _announce(self, chat_id: int, text: str, reply_to: int, audio: bool, edited: bool) -> str:
        self.tg.send_chat_action(chat_id, "typing")
        result = self.build_script(text, self.cfg)
        heading = "Updated script:\n\n" if edited else ""
        self.tg.send_message(chat_id, heading + result.display, reply_to)
        notes = [result.note] if result.note else []
        if audio and result.pronounced:
            items = list(result.pronounced.items())
            spelled = "; ".join(f"{name} as {spoken}" for name, spoken in items[:NOTE_NAMES])
            more = f" and {len(items) - NOTE_NAMES} more" if len(items) > NOTE_NAMES else ""
            notes.append(f"Names pronounced: {spelled}{more}. To correct one, send /say Name Re-spell-ing")
        for note in notes:
            self.tg.send_message(chat_id, f"Note: {note}")
        log.info("script source=%s", result.source)
        if not audio:
            return "preview"

        date = datetime.now(WAT).strftime("%Y-%m-%d")
        engine = self._send_audio(chat_id, result.spoken, reply_to, f"{self.cfg.label} announcements {date}",
                                  f"announcements-{date}.mp3")
        if not engine:
            self.tg.send_message(
                chat_id,
                "I couldn't make the audio this time: every voice engine failed. "
                "The script above is ready to read aloud, or send the announcements again to retry.",
                reply_to,
            )
            return "no_audio"
        return "announced"

    def _send_audio(self, chat_id: int, spoken: str, reply_to: int, title: str, filename: str) -> str | None:
        """Voice the text and send it; returns the engine used, or None if every engine failed."""
        self.tg.send_chat_action(chat_id, "upload_voice")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / filename
            engines = self.engines_for(self.cfg, self.gender)
            try:
                engine = voice.synthesize(spoken, out, engines)
            except voice.VoiceError:
                self.failures += 1
                log.error("tts outcome=failed")
                return None
            caption = title + ("" if engine == engines[0][0] else f" (backup voice: {engine})")
            self.tg.send_audio(chat_id, out, title=title, caption=caption, reply_to=reply_to)
        log.info("tts engine=%s", engine)
        return engine

    # -- /say and /unsay: pronunciation corrections from Telegram ---------------------
    def _say_command(self, chat_id: int, cmd: str, arg: str, reply_to: int) -> str:
        parts = arg.split(None, 1)
        if not parts or not lexicon_store.NAME.match(parts[0]):
            self.tg.send_message(chat_id, "Send /say Name Re-spell-ing, for example /say Tonte Ton-teh. "
                                          "Send /say Name to hear how it is said now.", reply_to)
            return "help"
        name = parts[0]

        if cmd == "unsay":
            if not self.lexicon.set_entry(name, None):
                self.tg.send_message(chat_id, f"{name} is not in the corrections list.", reply_to)
                return "help"
            saved = self._publish(chat_id, f"Pronunciation: remove {name}", reply_to)
            auto = speech.spoken_form(name, speech.load_lexicon()) or name
            self.tg.send_message(chat_id, f"Removed. {name} will be worked out automatically again: {auto}.", reply_to)
            return "say_removed" if saved else "say_unsaved"

        if len(parts) == 1:
            lex = speech.load_lexicon()
            spoken = speech.spoken_form(name, lex)
            how = ("from your corrections" if name.lower() in lex
                   else "worked out automatically" if spoken else "read as written")
            self.tg.send_message(chat_id, f"{name} is said as {spoken or name} ({how}). "
                                          f"To change it: /say {name} Re-spell-ing", reply_to)
            self._send_audio(chat_id, f"{spoken or name}.", reply_to, f"How {name} is said", "pronunciation.mp3")
            return "say_checked"

        spelling = " ".join(parts[1].split())
        if not lexicon_store.SPELLING.match(spelling):
            self.tg.send_message(chat_id, "Use letters, hyphens and spaces only for the respelling, "
                                          "for example /say Tonte Ton-teh.", reply_to)
            return "help"
        self.lexicon.set_entry(name, spelling)
        saved = self._publish(chat_id, f"Pronunciation: {name}", reply_to)
        if saved:
            self.tg.send_message(chat_id, f"Saved. {name} will be said as {spelling} from now on.", reply_to)
        self._send_audio(chat_id, f"{spelling}.", reply_to, f"How {name} is said", "pronunciation.mp3")
        return "say_saved" if saved else "say_unsaved"

    def _publish(self, chat_id: int, message: str, reply_to: int) -> bool:
        try:
            self.lexicon.publish(message)
            return True
        except lexicon_store.LexiconError:
            self.failures += 1
            log.error("lexicon outcome=push_failed")
            self.tg.send_message(chat_id, "I used the change for now but could not save it on GitHub, "
                                          "so it may be lost. Please send it again later.", reply_to)
            return False


def run(tg: Telegram, announcer: Announcer, deadline: float | None = None, clock=time.time) -> None:
    offset = None
    while True:
        remaining = (deadline - clock()) if deadline else 0
        updates = tg.get_updates(offset, timeout=int(min(50, max(0, remaining))))
        for update in updates:
            announcer.process(update)
            offset = update["update_id"] + 1
        if not updates and (deadline is None or clock() >= deadline):
            return


def deadline_today(hhmm: str, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    hour, minute = (int(x) for x in hhmm.split(":"))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Church Announcer: one polling run.")
    parser.add_argument("--listen-until", metavar="HH:MM", help="keep listening until this UTC time today")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("httpx", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    try:
        cfg = config.load()
    except config.ConfigError as exc:
        log.error("%s", exc)
        return 2

    tg = Telegram(cfg.telegram_token, cfg.telegram_api)
    deadline = deadline_today(args.listen_until) if args.listen_until else None
    try:
        announcer = Announcer(cfg, tg)
        log.info("run start listen=%s gemini=%s", bool(deadline), cfg.gemini_enabled)
        run(tg, announcer, deadline)
    except TelegramError as exc:
        log.error("telegram error: %s", exc)
        return 1
    log.info("run done %s", " ".join(f"{k}={v}" for k, v in sorted(announcer.stats.items())) or "no messages")
    return 1 if announcer.failures else 0


if __name__ == "__main__":
    sys.exit(main())
