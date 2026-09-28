"""Minimal Telegram Bot API client.

Errors never include the request URL, because it contains the bot token and the
Actions logs of a public repo are public.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

MAX_MESSAGE = 4096


class TelegramError(RuntimeError):
    pass


def split_text(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    """Split on paragraph, then line, then word boundaries to fit Telegram's limit."""
    chunks: list[str] = []
    rest = text.strip()
    while len(rest) > limit:
        cut = max(rest.rfind("\n\n", 0, limit), rest.rfind("\n", 0, limit), rest.rfind(" ", 0, limit))
        if cut <= 0:
            cut = limit
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        chunks.append(rest)
    return chunks


class Telegram:
    def __init__(self, token: str, api_base: str, session: requests.Session | None = None):
        self._base = f"{api_base}/bot{token}/"
        self._http = session or requests.Session()

    def _call(self, method: str, *, timeout: float = 30, files=None, **params):
        try:
            if files:
                resp = self._http.post(self._base + method, data=params, files=files, timeout=timeout)
            else:
                resp = self._http.post(self._base + method, json=params, timeout=timeout)
            body = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise TelegramError(f"{method}: {type(exc).__name__}") from None
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('error_code')} {body.get('description')}")
        return body["result"]

    def get_me(self) -> dict:
        return self._call("getMe")

    def get_webhook_info(self) -> dict:
        return self._call("getWebhookInfo")

    def get_updates(self, offset: int | None = None, timeout: int = 0, limit: int = 100) -> list[dict]:
        params = {"timeout": timeout, "limit": limit, "allowed_updates": ["message", "edited_message"]}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", timeout=timeout + 15, **params)

    def ack(self, update_id: int) -> None:
        """Confirm every update up to and including update_id, so no later run sees it again."""
        self._call("getUpdates", offset=update_id + 1, timeout=0, limit=1)

    def send_message(self, chat_id: int, text: str, reply_to: int | None = None) -> None:
        for i, chunk in enumerate(split_text(text)):
            params = {"chat_id": chat_id, "text": chunk}
            if reply_to and i == 0:
                params["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
            self._call("sendMessage", **params)

    def send_audio(self, chat_id: int, path: Path, title: str, caption: str = "", reply_to: int | None = None) -> None:
        params = {"chat_id": chat_id, "title": title, "caption": caption[:1024]}
        if reply_to:
            params["reply_parameters"] = json.dumps({"message_id": reply_to, "allow_sending_without_reply": True})
        with open(path, "rb") as fh:
            self._call("sendAudio", timeout=120, files={"audio": (path.name, fh, "audio/mpeg")}, **params)

    def send_chat_action(self, chat_id: int, action: str) -> None:
        try:
            self._call("sendChatAction", chat_id=chat_id, action=action)
        except TelegramError:
            pass  # cosmetic only

    def get_short_description(self) -> str:
        return self._call("getMyShortDescription").get("short_description", "")

    def set_short_description(self, text: str) -> None:
        self._call("setMyShortDescription", short_description=text[:120])
