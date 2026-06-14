"""Unit tests for the pure parsing heuristics."""

import unittest

from logfinder.parse import (
    chat_content, detect_session_user, extract_speaker, is_chat_line,
    parse_time, sanitize, segment_colors, split_prefix,
)


class SpeakerTests(unittest.TestCase):
    def test_real_player_messages(self):
        cases = {
            "Party > [MVP++] ViciousVelvet: hi": "ViciousVelvet",
            "? Legend [MVP++] velvixt: gg": "velvixt",
            "Apprentice Mattnurit: gg": "Mattnurit",
            "[MVP++] Name: msg": "Name",
            "Name: msg": "Name",
            "Name [Member]: msg": "Name",
            "Friend > [VIP] Trtlz: yo": "Trtlz",
        }
        for content, expected in cases.items():
            self.assertEqual(extract_speaker(content), expected, content)

    def test_system_lines_are_none(self):
        for content in [
            "Player eliminated: galusss (100%)",
            "Total Fails: 3",
            "Your Score: 4",
            "Automatically activated: Speed Boost",
            "------ Guild: MOTD here",
            "[NPC] Festive Guide: welcome",
            '{"server":"dynamiclobby11A","gametype":"HOUSING"}',
            "FearlessFloppy got a perfect build in 9.4s!",
            "Friend > YaoiTwin joined.",
            "You reached Checkpoint #1 after 00:29.677.",
        ]:
            self.assertIsNone(extract_speaker(content), content)


class LineFactTests(unittest.TestCase):
    def test_is_chat_and_content(self):
        raw = "[23:09:34] [Client thread/INFO]: [CHAT] Name: hi"
        self.assertTrue(is_chat_line(raw))
        self.assertEqual(chat_content(raw), "Name: hi")
        sys = "[23:09:34] [Client thread/INFO]: Setting user: Floppy_Banana"
        self.assertFalse(is_chat_line(sys))
        self.assertEqual(chat_content(sys), "")

    def test_split_prefix(self):
        raw = "[23:09:34] [Client thread/INFO]: [CHAT] §6Name§f: hi"
        prefix, payload = split_prefix(raw)
        self.assertEqual(prefix, "[23:09:34] [Client thread/INFO]: [CHAT] ")
        self.assertEqual(payload, "§6Name§f: hi")
        sysraw = "[23:09:34] [Client thread/INFO]: Setting user: Floppy_Banana"
        p2, pay2 = split_prefix(sysraw)
        self.assertEqual(p2, "[23:09:34] [Client thread/INFO]: ")
        self.assertEqual(pay2, "Setting user: Floppy_Banana")

    def test_parse_time(self):
        self.assertEqual(parse_time("[23:56:05] [x]: hi"), 86165)
        self.assertEqual(parse_time("[00:00:00] x"), 0)
        self.assertIsNone(parse_time("[00:38:390] not a time"))
        self.assertIsNone(parse_time("no timestamp here"))

    def test_detect_session_user(self):
        lines = [
            "[00:27:48] [Client thread/INFO]: starting",
            "[00:28:00] [Client thread/INFO]: [LC] Setting user: Floppy_Banana",
        ]
        self.assertEqual(detect_session_user(lines), "Floppy_Banana")
        self.assertIsNone(detect_session_user(["nothing here", "still nothing"]))

    def test_sanitize_strips_control_chars(self):
        self.assertEqual(sanitize("a\rb\x00c\r"), "abc")


class ColorTests(unittest.TestCase):
    def test_segment_colors_splits_runs(self):
        runs = segment_colors("§6[MVP§5++§6] velvixt§f: hi")
        # reconstruct visible text == strip of codes
        self.assertEqual("".join(t for t, _ in runs), "[MVP++] velvixt: hi")
        keys = [k for _, k in runs]
        self.assertIn("6", keys)
        self.assertIn("5", keys)
        self.assertIn("f", keys)

    def test_reset_clears_color(self):
        runs = segment_colors("§ahello§rworld")
        self.assertEqual(runs[0], ("hello", "a"))
        self.assertEqual(runs[-1], ("world", None))

    def test_plain_text_one_run(self):
        self.assertEqual(segment_colors("plain"), [("plain", None)])


if __name__ == "__main__":
    unittest.main()
