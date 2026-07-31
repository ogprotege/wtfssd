from __future__ import annotations

import unittest
from pathlib import Path

from wtfssd.collectors import processes

FIXTURE = (Path(__file__).parent / "fixtures" / "ps.txt").read_text()

SAMPLE = """  PID  PPID     ELAPSED    RSS COMM
    1     0 27-00:00:00  28176 /sbin/launchd
  687     1 02-16:29:40   5504 /System/Library/Frameworks/com.apple.CodeSigningHelper
 9001     1 27-01:00:00 4160000 /Applications/Cursor.app/Contents/Frameworks/Cursor Helper.app/Contents/MacOS/Cursor Helper
 9002  9001 00:05:12  200000 /Applications/Cursor.app/Contents/MacOS/Cursor
 9003     1 12-00:00:00  900000 /Applications/Claude.app/Contents/MacOS/Claude
"""


def fake_runner(text):
    def run(argv, timeout=15):
        return text
    return run


class TestEtime(unittest.TestCase):
    def test_mm_ss(self):
        self.assertEqual(processes.etime_to_seconds("05:12"), 312)

    def test_hh_mm_ss(self):
        self.assertEqual(processes.etime_to_seconds("01:03:27"), 3807)

    def test_dd_hh_mm_ss(self):
        self.assertEqual(processes.etime_to_seconds("02-16:31:34"),
                         2 * 86400 + 16 * 3600 + 31 * 60 + 34)


class TestIsIde(unittest.TestCase):
    def test_matches_ides(self):
        self.assertTrue(processes.is_ide_process("/Applications/Cursor.app/Contents/MacOS/Cursor"))
        self.assertTrue(processes.is_ide_process("/Applications/Claude.app/Contents/MacOS/Claude"))
        self.assertTrue(processes.is_ide_process("/Applications/Visual Studio Code.app/Contents/MacOS/Electron"))
        self.assertTrue(processes.is_ide_process("/Users/x/.vscode/extensions/Code Helper"))

    def test_excludes_system(self):
        self.assertFalse(processes.is_ide_process("/System/Library/Frameworks/com.apple.CodeSigningHelper"))
        self.assertFalse(processes.is_ide_process("/sbin/launchd"))
        self.assertFalse(processes.is_ide_process("/usr/libexec/smd"))


class TestParsePs(unittest.TestCase):
    def test_ghost_detection(self):
        rep = processes.parse_ps(SAMPLE, ghost_seconds=3 * 86400)
        names = [g.name for g in rep.ghosts]
        # 27-day Cursor Helper and 12-day Claude are ghosts; 5-min Cursor is not
        self.assertEqual(len(rep.ghosts), 2)
        self.assertTrue(any("Cursor Helper" in n for n in names))
        self.assertTrue(any("Claude" in n for n in names))
        # CodeSigningHelper (system path, "Code" substring) must not match
        self.assertEqual(rep.total_ide_processes, 3)
        ghost = rep.ghosts[0]
        self.assertEqual(ghost.pid, 9001)
        self.assertEqual(ghost.rss_mb, 4160000 / 1024)

    def test_fixture_parses_without_error(self):
        rep = processes.parse_ps(FIXTURE, ghost_seconds=3 * 86400)
        self.assertGreaterEqual(rep.total_ide_processes, 0)  # just don't crash

    def test_collect_failure_degrades(self):
        rep = processes.collect_processes(runner=fake_runner(None))
        self.assertEqual(rep.ghosts, [])
        self.assertEqual(rep.total_ide_processes, 0)
        self.assertIsNotNone(rep.note)

    def test_ide_procs_all_ages_sorted_by_rss(self):
        text = (Path(__file__).parent / "fixtures" / "ps.txt").read_text()
        rep = processes.parse_ps(text, ghost_seconds=3 * 86400)
        self.assertGreaterEqual(len(rep.ide_procs), len(rep.ghosts))
        self.assertEqual(rep.total_ide_processes, len(rep.ide_procs))
        rss = [p.rss_mb for p in rep.ide_procs]
        self.assertEqual(rss, sorted(rss, reverse=True))
        # ghosts are a subset of ide_procs by pid
        self.assertTrue({g.pid for g in rep.ghosts} <=
                        {p.pid for p in rep.ide_procs})


if __name__ == "__main__":
    unittest.main()
