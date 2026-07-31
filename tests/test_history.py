from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from ssdwtf import models
from ssdwtf import history


def make_report(ts: str, units: int | None, state_bytes: int,
                note: str | None = None) -> models.HealthReport:
    rep = models.make_empty_report(ts, 64.0)
    rep.smart = models.SmartReport(available=units is not None,
                                   data_units_written=units,
                                   tb_written=(units or 0) * 512_000 / 1e12)
    rep.statedirs = models.StateDirReport(dirs=[], total_bytes=state_bytes,
                                          note=note)
    return rep


class TestHistory(unittest.TestCase):
    def test_append_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            dd = Path(td)
            history.append_history(make_report("2026-07-29T10:00:00", 1_000_000, 5_000), data_dir=dd)
            history.append_history(make_report("2026-07-30T10:00:00", 2_000_000, 6_000), data_dir=dd)
            loaded = history.load_history(data_dir=dd)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].smart.data_units_written, 1_000_000)
        self.assertEqual(loaded[1].statedirs.total_bytes, 6_000)

    def test_load_skips_corrupt_lines(self):
        with tempfile.TemporaryDirectory() as td:
            dd = Path(td)
            history.append_history(make_report("2026-07-30T10:00:00", 5, 5), data_dir=dd)
            with history.history_path(dd).open("a") as fh:
                fh.write("{corrupt json line\n")
            loaded = history.load_history(data_dir=dd)
        self.assertEqual(len(loaded), 1)

    def test_load_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(history.load_history(data_dir=Path(td)), [])

    def test_load_limit_returns_newest(self):
        with tempfile.TemporaryDirectory() as td:
            dd = Path(td)
            for i in range(5):
                history.append_history(make_report(f"2026-07-2{i}T10:00:00", i, i), data_dir=dd)
            loaded = history.load_history(limit=2, data_dir=dd)
        self.assertEqual([r.smart.data_units_written for r in loaded], [3, 4])

    def test_write_rate(self):
        h = [make_report("2026-07-29T10:00:00", 1_000_000, 0),
             make_report("2026-07-30T10:00:00", 3_000_000, 0)]
        # 2,000,000 units * 512,000 bytes / 1 day = 1024 GB/day
        self.assertAlmostEqual(history.gb_written_per_day(h), 1024.0)

    def test_write_rate_none_when_insufficient(self):
        self.assertIsNone(history.gb_written_per_day([]))
        self.assertIsNone(history.gb_written_per_day([make_report("2026-07-30T10:00:00", 5, 0)]))
        same = [make_report("2026-07-30T10:00:00", 5, 0),
                make_report("2026-07-30T10:30:00", 6, 0)]  # < 1 hour window
        self.assertIsNone(history.gb_written_per_day(same))

    def test_state_growth_rate(self):
        now = datetime.now()
        h = [make_report((now - timedelta(days=1)).isoformat(), None, 1_000_000_000),
             make_report(now.isoformat(), None, 3_000_000_000)]
        self.assertAlmostEqual(history.state_growth_gb_per_day(h), 2.0)

    def test_state_growth_ignores_uncollected_fast_rows(self):
        now = datetime.now()
        day = timedelta(days=1)
        fast = "not collected (--fast)"
        # fast row in the middle: growth reflects 10 → 11 GB only
        h = [make_report((now - day).isoformat(), None, 10_000_000_000),
             make_report((now - day / 2).isoformat(), None, 0, note=fast),
             make_report(now.isoformat(), None, 11_000_000_000)]
        self.assertAlmostEqual(history.state_growth_gb_per_day(h), 1.0)
        # fast row at the window start must not inflate the delta
        h = [make_report((now - 2 * day).isoformat(), None, 0, note=fast),
             make_report((now - day).isoformat(), None, 10_000_000_000),
             make_report(now.isoformat(), None, 11_000_000_000)]
        self.assertAlmostEqual(history.state_growth_gb_per_day(h), 1.0)

    def test_state_growth_window_excludes_old_step(self):
        now = datetime.now()
        day = timedelta(days=1)
        # a one-time +999 GB step 19 days ago (e.g. registry expansion) is
        # older than the 14-day fitting window and must not inflate the slope
        h = [make_report((now - 20 * day).isoformat(), None, 1_000_000_000),
             make_report((now - 19 * day).isoformat(), None, 1_000_000_000_000),
             make_report((now - day).isoformat(), None, 1_001_000_000_000),
             make_report(now.isoformat(), None, 1_002_000_000_000)]
        # slope fits only the trailing window: 1 GB over 1 day
        self.assertAlmostEqual(history.state_growth_gb_per_day(h), 1.0)


if __name__ == "__main__":
    unittest.main()
