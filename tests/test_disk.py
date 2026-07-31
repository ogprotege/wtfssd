from __future__ import annotations

import unittest
from pathlib import Path

from wtfssd.collectors import disk

FIXTURE = (Path(__file__).parent / "fixtures" / "df.txt").read_text()


def fake_runner(text):
    def run(argv, timeout=15):
        return text
    return run


class TestDisk(unittest.TestCase):
    def test_parse_fixture(self):
        rep = disk.parse_df(FIXTURE, "/System/Volumes/Data")
        self.assertEqual(rep.mount, "/System/Volumes/Data")
        self.assertGreater(rep.size_gb, 0)
        self.assertGreater(rep.avail_gb, 0)
        self.assertAlmostEqual(rep.pct_used + rep.pct_free, 100.0, places=1)

    def test_parse_exact(self):
        text = ("Filesystem 1024-blocks Used Avail Capacity iused ifree %iused Mounted on\n"
                "/dev/disk3s5 971749180 544667648 404724800 58% 1 2 0% /System/Volumes/Data\n")
        rep = disk.parse_df(text, "/System/Volumes/Data")
        self.assertAlmostEqual(rep.size_gb, 971749180 * 1024 / 1e9, places=3)
        self.assertEqual(rep.pct_used, 58.0)
        self.assertEqual(rep.pct_free, 42.0)

    def test_collect_none_on_failure(self):
        self.assertIsNone(disk.collect_disk(runner=fake_runner(None)))


if __name__ == "__main__":
    unittest.main()
