from __future__ import annotations

import unittest
from pathlib import Path

from ssdwtf.collectors import apfs

FIX = Path(__file__).parent / "fixtures"


def _runner(cmd):
    if "listlocalsnapshots" in cmd:
        return (FIX / "tmutil_snapshots.txt").read_text()
    if cmd[:1] == ["diskutil"]:
        return (FIX / "diskutil_info.txt").read_text()
    return None


class TestApfs(unittest.TestCase):
    def test_parse_names_empty(self):
        text = (FIX / "tmutil_snapshots.txt").read_text()
        self.assertEqual(apfs.parse_snapshot_names(text), [])

    def test_parse_names_multi(self):
        text = ("Snapshots for disk /:\n"
                "com.apple.TimeMachine.2026-07-20-090001\n"
                "com.apple.TimeMachine.2026-07-28-113002\n")
        self.assertEqual(len(apfs.parse_snapshot_names(text)), 2)

    def test_snapshot_age(self):
        import datetime as dt
        now = dt.datetime(2026, 7, 30, 12, 0, 0).timestamp()
        age = apfs.snapshot_age_days(
            "com.apple.TimeMachine.2026-07-20-120000", now)
        self.assertIsNotNone(age)
        self.assertAlmostEqual(age, 10.0, places=1)
        self.assertIsNone(apfs.snapshot_age_days("no-date-here", now))

    def test_parse_diskutil_info(self):
        text = (FIX / "diskutil_info.txt").read_text()
        info = apfs.parse_diskutil_info(text)
        self.assertAlmostEqual(info["container_free_gb"], 412.6, places=0)
        self.assertAlmostEqual(info["volume_used_gb"], 558.4, places=0)

    def test_collect_real_fixtures(self):
        rep = apfs.collect_apfs("/System/Volumes/Data", runner=_runner)
        self.assertTrue(rep.available)
        self.assertEqual(rep.snapshot_count, 0)
        self.assertIsNone(rep.oldest_snapshot_days)
        self.assertAlmostEqual(rep.container_free_gb, 412.6, places=0)

    def test_collect_degrades(self):
        rep = apfs.collect_apfs("/System/Volumes/Data",
                                runner=lambda cmd: None)
        self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
