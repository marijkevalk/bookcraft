"""Tiny local config store for the web UI (remembers the user's API key).

Stored in the user's home dir as ``~/.bookcraft/config.json`` with owner-only
permissions. Cross-platform (no extra dependency). The API key never leaves
this machine — it is sent only to the model provider the user chose.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
from pathlib import Path

CONFIG_DIR = Path.home() / ".bookcraft"
CONFIG_PATH = CONFIG_DIR / "config.json"


def load_config() -> dict[str, str]:
    """Return the saved config, or an empty dict if none/unreadable."""
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(values: dict[str, str]) -> None:
    """Merge ``values`` into the saved config, writing owner-only (0600)."""
    current = load_config()
    current.update(values)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    with contextlib.suppress(OSError):
        # best-effort on platforms without POSIX perms
        os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600


def get_saved_api_key() -> str:
    return load_config().get("gemini_api_key", "")
