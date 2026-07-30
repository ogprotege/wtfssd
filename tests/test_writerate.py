from __future__ import annotations

import unittest
from pathlib import Path

from ssdwtf.collectors import writerate

FIX = Path(__file__).parent / "fixtures"


class TestWriteRate(unittest.TestCase):
    def test_parse_real_fixture(self):
        text = (FIX / "iostat.txt").read_text()
        # fixture samples: 6.52 (since-boot avg) then 1.33 (interval)
        self.assertEqual(writerate.parse_iostat(text), 1.33)

    def test_parse_garbage(self):
        self.assertIsNone(writerate.parse_iostat("no data here"))
        self.assertIsNone(writerate.parse_iostat(""))

    def test_collect(self):
        rep = writerate.collect_writerate(
            "disk0", runner=lambda cmd: (FIX / "iostat.txt").read_text())
        self.assertTrue(rep.available)
        self.assertEqual(rep.mb_per_s, 1.33)

    def test_collect_degrades(self):
        rep = writerate.collect_writerate("disk0", runner=lambda cmd: None)
        self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
