import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from announcer.config import Config  # noqa: E402
from announcer.script import Script  # noqa: E402
from announcer.telegram import TelegramError  # noqa: E402

GROUP = -1001234567890
PRIVATE = 555
STRANGER = 777
BOT_ID = 999


class FakeTelegram:
    """Mimics Bot API update confirmation: an update disappears once a later offset is requested."""

    def __init__(self, updates=(), fail_sends=False, send_error="sendMessage: 500 Internal"):
        self.queue = list(updates)
        self.messages, self.audio, self.actions = [], [], []
        self.description = ""
        self.fail_sends = fail_sends
        self.send_error = send_error

    def get_me(self):
        return {"id": BOT_ID, "username": "DoxaAnnouncerBot"}

    def get_updates(self, offset=None, timeout=0, limit=100):
        if offset is not None:
            self.queue = [u for u in self.queue if u["update_id"] >= offset]
        return self.queue[:limit]

    def ack(self, update_id):
        self.get_updates(update_id + 1, 0, 1)

    def send_message(self, chat_id, text, reply_to=None):
        if self.fail_sends:
            raise TelegramError(self.send_error)
        self.messages.append((chat_id, text))

    def send_audio(self, chat_id, path, title, caption="", reply_to=None):
        self.audio.append((chat_id, path.name, path.read_bytes(), caption))

    def send_chat_action(self, chat_id, action):
        self.actions.append(action)

    def get_short_description(self):
        return self.description

    def set_short_description(self, text):
        self.description = text


def make_update(update_id, text, chat_id=PRIVATE, chat_type="private", reply_to_from=None, edited=False):
    msg = {
        "message_id": update_id * 10,
        "chat": {"id": chat_id, "type": chat_type},
        "from": {"id": 42, "is_bot": False},
        "text": text,
    }
    if reply_to_from is not None:
        msg["reply_to_message"] = {"message_id": 1, "from": {"id": reply_to_from}}
    return {"update_id": update_id, ("edited_message" if edited else "message"): msg}


@pytest.fixture
def cfg():
    return Config(
        telegram_token="t",
        allowed_chat_ids=frozenset({GROUP, PRIVATE}),
        church_name="Doxa Family Church",
        gemini_api_key="k",
        gemini_model="m",
        default_voice="en-NG-EzinneNeural",
        edge_voices={"female": "en-NG-EzinneNeural", "male": "en-NG-AbeoNeural"},
        voice_rate="-15%",
        piper_voices={"female": "pf", "male": "pm"},
        piper_dir="unused",
        telegram_api="https://example.invalid",
        min_group_words=6,
    )


def fake_script(text, cfg):
    return Script(f"SCRIPT: {text}", "gemini")


class EngineSpy:
    def __init__(self):
        self.genders = []

    def __call__(self, cfg, gender):
        self.genders.append(gender)

        def write(text, out):
            out.write_bytes(b"ID3fake")

        return [("edge-tts", write)]
