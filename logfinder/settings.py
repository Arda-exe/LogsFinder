"""Tiny JSON settings store — remembers the last-used logs folder between launches.

Stored under the user's AppData dir (not next to the .exe, since the onefile exe
runs from a temp dir). All operations are best-effort: any IO/parse error just
means settings don't persist, never a crash.
"""

import json
import os
from pathlib import Path


def _settings_path():
    base = os.environ.get("APPDATA")
    root = Path(base) if base else (Path.home() / ".config")
    return root / "LogsFinder" / "settings.json"


def load_settings():
    """Return the saved settings dict (empty dict if none / unreadable)."""
    try:
        with open(_settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    """Write the settings dict; silently no-op if it can't be written."""
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass  # non-fatal: settings just won't persist this time
