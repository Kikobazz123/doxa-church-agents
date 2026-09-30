"""Save pronunciation corrections sent with /say, and commit them back to the repo.

In GitHub Actions the checkout already holds a token that can push (the job has
contents: write), so a correction made in Telegram is saved for every later run
without anyone opening GitHub or VS Code. Outside Actions the file is only
written locally.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path

from .speech import LEXICON_PATH

log = logging.getLogger("announcer")

NAME = re.compile(r"^[^\W\d_][\w'’-]{0,39}$")
SPELLING = re.compile(r"^[^\W\d_](?:[^\W\d_]|['’ -]){0,59}$")


class LexiconError(RuntimeError):
    pass


def _path() -> Path:
    return Path(os.environ.get("PRONUNCIATIONS_FILE") or LEXICON_PATH)


def read() -> dict[str, str]:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(data: dict[str, str]) -> None:
    _path().write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def set_entry(name: str, spelling: str | None) -> bool:
    """Add/replace (spelling) or remove (None) an entry, matching the name case-insensitively.
    Returns False when removing a name that isn't there."""
    data = read()
    existing = next((k for k in data if k.lower() == name.lower()), None)
    if spelling is None:
        if existing is None:
            return False
        del data[existing]
    else:
        data.pop(existing, None)
        data[name[:1].upper() + name[1:]] = spelling
    _write(data)
    return True


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=120)


def publish(message: str) -> None:
    """Commit pronunciations.json and push. No-op outside GitHub Actions."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        log.info("lexicon saved locally only (not in GitHub Actions)")
        return
    path = str(_path())
    if _git("add", path).returncode or _git("commit", "-m", message, "--", path).returncode:
        raise LexiconError("could not commit the change")
    for attempt in range(2):
        if _git("push").returncode == 0:
            log.info("lexicon pushed")
            return
        _git("pull", "--rebase")          # someone else pushed meanwhile: replay on top and retry
    raise LexiconError("could not push the change to GitHub")
