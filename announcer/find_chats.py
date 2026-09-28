"""Setup helper: show the chat IDs the bot can see, and why it might see none.

    python -m announcer.find_chats

Asks for the bot token (typed input stays hidden), and never confirms updates,
so the real announcer still gets every message afterwards.
"""

from __future__ import annotations

import getpass
import os
import sys

from .config import DEFAULT_TELEGRAM_API
from .telegram import Telegram, TelegramError


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or getpass.getpass("Paste the bot token (hidden) and press Enter: ").strip()
    tg = Telegram(token, os.environ.get("TELEGRAM_API_BASE", DEFAULT_TELEGRAM_API))

    try:
        me = tg.get_me()
    except TelegramError as exc:
        print(f"\nThe token was rejected ({exc}). Copy it again from @BotFather: /mybots, your bot, API Token.")
        return 1
    print(f"\nBot: @{me.get('username')}")

    problems = 0
    if not me.get("can_read_all_group_messages"):
        problems += 1
        print("\n[!] Privacy mode is still ON, so the bot can't see normal group messages.\n"
              "    Fix: @BotFather, /setprivacy, choose the bot, Disable.\n"
              "    Then REMOVE the bot from the group and ADD it again. The change only applies to groups joined afterwards.")

    hook = tg.get_webhook_info()
    if hook.get("url"):
        problems += 1
        print("\n[!] A webhook is set on this bot, which blocks reading messages this way.\n"
              "    Fix: open this in a browser, replacing <TOKEN>, then run this helper again:\n"
              "    https://api.telegram.org/bot<TOKEN>/deleteWebhook")

    chats = {}
    for update in tg.get_updates(timeout=0):
        chat = (update.get("message") or update.get("edited_message") or {}).get("chat")
        if chat:
            name = chat.get("title") or " ".join(
                x for x in (chat.get("first_name"), chat.get("last_name")) if x) or chat.get("username", "")
            chats[chat["id"]] = (name, chat.get("type"))

    if not chats:
        print(f"\nNo messages found yet. Try this:\n"
              f"  1. In the group, send:  /help@{me.get('username')}\n"
              f"     (commands to the bot always get through, even with privacy on)\n"
              f"  2. Run this helper again within a few minutes.\n"
              f"  Messages older than 24 hours are no longer available.")
        return 1

    print("\nChats the bot can see:\n")
    for chat_id, (name, kind) in chats.items():
        print(f"  {chat_id:>16}   {kind:<10}  {name}")
    groups = [str(c) for c, (_, k) in chats.items() if k in ("group", "supergroup")]
    if groups:
        print(f"\nFor the ALLOWED_CHAT_IDS secret, use the group's number, including the minus sign: {','.join(groups)}")
    if problems:
        print("\nFix the [!] items above too, or the bot won't hear ordinary announcements.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
