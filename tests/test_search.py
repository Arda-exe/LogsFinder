"""Unit tests for the search core (scope, dates, speaker breakdown)."""

import datetime
import unittest
from pathlib import Path

from logfinder.parse import LogFile, build_line
from logfinder.search import search


def make_logfile(name, raw_lines, session_user=None, date=None):
    return LogFile(name=name, lines=[build_line(r) for r in raw_lines],
                   session_user=session_user, date=date)


class FakeCache:
    def __init__(self, mapping):  # {Path: LogFile}
        self.mapping = mapping

    def get_file(self, path):
        return self.mapping.get(path)


CHAT = "[12:00:00] [Client thread/INFO]: [CHAT] "
SYS = "[12:00:01] [Client thread/INFO]: "


class SearchTests(unittest.TestCase):
    def _setup(self):
        lines = [
            CHAT + "§6[MVP++] Alice§f: nice build gg",   # 0  chat, Alice
            SYS + "[STDOUT]: nice internal log",          # 1  system, has 'nice'
            CHAT + "Bob: that build was nice",            # 2  chat, Bob
            CHAT + "Player eliminated: nicebot (50%)",    # 3  system chat (no speaker)
        ]
        lf = make_logfile("2025-12-04-1.log.gz", lines, session_user="Alice",
                          date=datetime.date(2025, 12, 4))
        p = Path("2025-12-04-1.log.gz")
        return FakeCache({p: lf}), [p]

    def test_scope_all_counts_and_speakers(self):
        cache, files = self._setup()
        r = search(cache, files, "nice", scope="all")
        self.assertEqual(r.total_count, 4)
        self.assertEqual(sum(r.speakers.values()), r.total_count)
        self.assertEqual(r.speakers["Alice"], 1)
        self.assertEqual(r.speakers["Bob"], 1)
        self.assertEqual(r.speakers["system"], 2)  # the STDOUT line + the eliminated line
        self.assertIn("Alice", r.self_names)

    def test_scope_chat_excludes_system_log(self):
        cache, files = self._setup()
        r = search(cache, files, "nice", scope="chat")
        # excludes the STDOUT line; still includes the eliminated [CHAT] line as system
        self.assertEqual(r.total_count, 3)
        self.assertNotIn("STDOUT", "".join(
            lv.stripped for b in r.blocks for lv in b.lines if lv.is_match))

    def test_scope_mine_only_session_user(self):
        cache, files = self._setup()
        r = search(cache, files, "nice", scope="mine")
        self.assertEqual(r.total_count, 1)
        self.assertEqual(list(r.speakers), ["Alice"])

    def test_date_prefilter_excludes_out_of_range(self):
        cache, files = self._setup()
        r = search(cache, files, "nice", date_from=datetime.date(2026, 1, 1))
        self.assertEqual(r.files_searched, 0)
        self.assertEqual(r.total_count, 0)
        r2 = search(cache, files, "nice",
                    date_from=datetime.date(2025, 12, 1),
                    date_to=datetime.date(2025, 12, 31))
        self.assertEqual(r2.files_searched, 1)
        self.assertEqual(r2.total_count, 4)

    def test_no_match(self):
        cache, files = self._setup()
        r = search(cache, files, "zzz_not_here")
        self.assertEqual(r.total_count, 0)
        self.assertEqual(r.blocks, [])

    def test_blocks_carry_raw_for_coloring(self):
        cache, files = self._setup()
        r = search(cache, files, "nice", scope="all", context=0)
        matched = [lv for b in r.blocks for lv in b.lines if lv.is_match]
        alice = next(lv for lv in matched if lv.speaker == "Alice")
        self.assertIn("§", alice.raw)  # raw keeps the color codes


if __name__ == "__main__":
    unittest.main()
