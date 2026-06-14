"""Unit tests for the settings store (uses a temp APPDATA — never touches real settings)."""

import os
import tempfile
import unittest

from logfinder import settings


class SettingsTests(unittest.TestCase):
    def test_missing_then_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("APPDATA")
            os.environ["APPDATA"] = tmp
            try:
                self.assertEqual(settings.load_settings(), {})  # nothing saved yet
                settings.save_settings({"folder": r"D:\some\logs"})
                self.assertEqual(settings.load_settings().get("folder"), r"D:\some\logs")
            finally:
                if old is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = old

    def test_corrupt_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("APPDATA")
            os.environ["APPDATA"] = tmp
            try:
                p = settings._settings_path()
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("not json{", encoding="utf-8")
                self.assertEqual(settings.load_settings(), {})
            finally:
                if old is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = old


if __name__ == "__main__":
    unittest.main()
