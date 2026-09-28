"""The real client against a fake HTTP session: what actually goes over the wire."""

import pytest

from announcer.telegram import Telegram, TelegramError


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, result=None, ok=True):
        self.calls = []
        self.result, self.ok = result if result is not None else [], ok

    def post(self, url, json=None, data=None, files=None, timeout=None):
        self.calls.append({"method": url.rsplit("/", 1)[1], "params": json if json is not None else data,
                           "http_timeout": timeout, "files": files})
        if not self.ok:
            return FakeResponse({"ok": False, "error_code": 401, "description": "Unauthorized"})
        return FakeResponse({"ok": True, "result": self.result})


def client(session):
    return Telegram("SECRET-TOKEN", "https://example.invalid", session=session)


def test_long_poll_sends_telegram_timeout_and_longer_http_timeout():
    s = FakeSession()
    client(s).get_updates(offset=5, timeout=50)
    call = s.calls[0]
    assert call["method"] == "getUpdates"
    assert call["params"]["timeout"] == 50 and call["params"]["offset"] == 5
    assert call["http_timeout"] == 65


def test_ack_confirms_through_offset():
    s = FakeSession()
    client(s).ack(41)
    assert s.calls[0]["params"] == {"offset": 42, "timeout": 0, "limit": 1}


def test_send_audio_is_multipart(tmp_path):
    mp3 = tmp_path / "a.mp3"
    mp3.write_bytes(b"ID3")
    s = FakeSession(result={})
    client(s).send_audio(1, mp3, title="t", caption="c", reply_to=9)
    call = s.calls[0]
    assert call["method"] == "sendAudio" and "audio" in call["files"] and call["http_timeout"] == 120


def test_errors_never_leak_the_token():
    with pytest.raises(TelegramError) as exc:
        client(FakeSession(ok=False)).get_me()
    assert "SECRET-TOKEN" not in str(exc.value)
