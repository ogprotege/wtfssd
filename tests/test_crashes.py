from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from wtfssd.collectors import crashes

NOW = 1_785_500_000.0
APPS = ["Cursor", "Claude"]


def _make(dir: Path, name: str, age_days: float) -> None:
    p = dir / name
    p.write_text("{}")
    os.utime(p, (NOW - age_days * 86400, NOW - age_days * 86400))


class TestCrashes(unittest.TestCase):
    def test_app_from_filename(self):
        self.assertEqual(crashes.app_from_filename(
            "Cursor-2026-07-29-123456.ips"), "Cursor")
        self.assertEqual(crashes.app_from_filename(
            "Claude Helper-2026-07-29-010203.crash"), "Claude Helper")
        self.assertIsNone(crashes.app_from_filename("random.txt"))
        self.assertIsNone(crashes.app_from_filename("Cursor.ips"))

    def test_counts_recent_only(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _make(d, "Cursor-2026-07-29-123456.ips", 1)
            _make(d, "Cursor-2026-07-28-123456.ips", 3)
            _make(d, "Cursor-2026-07-20-123456.ips", 30)  # too old
            _make(d, "Claude-2026-07-29-123456.ips", 2)
            _make(d, "Safari-2026-07-29-123456.ips", 1)   # not watched
            rep = crashes.collect_crashes(APPS, dir=d, now=NOW)
            self.assertTrue(rep.available)
            self.assertEqual(rep.weekly, {"Cursor": 2, "Claude": 1})
            self.assertEqual(rep.total_weekly, 3)

    def test_helper_crashes_roll_up_to_parent_app(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _make(d, "Cursor Helper (Renderer)-2026-07-29-123456.ips", 1)
            _make(d, "Claude Helper (Plugin)-2026-07-29-123456.ips", 1)
            rep = crashes.collect_crashes(APPS, dir=d, now=NOW)
            self.assertEqual(rep.weekly, {"Cursor": 1, "Claude": 1})
            self.assertEqual(rep.total_weekly, 2)

    def test_missing_dir_is_zero_not_error(self):
        rep = crashes.collect_crashes(
            APPS, dir=Path("/nonexistent-diag-x"), now=NOW)
        self.assertTrue(rep.available)
        self.assertEqual(rep.total_weekly, 0)


if __name__ == "__main__":
    unittest.main()
