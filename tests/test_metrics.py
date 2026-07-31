from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wtfssd import metrics, models
from wtfssd.models import (ApfsReport, DiskReport, HealthReport, ProcessReport,
                           SmartReport, StateDir, StateDirReport, SwapReport,
                           make_empty_report)


def _report(ts: str, swap_mb: float) -> HealthReport:
    rep = make_empty_report(ts, 64.0)
    rep.smart = SmartReport(available=True, percent_used=2, tb_written=54.0,
                            available_spare=100, media_errors=0)
    rep.swap = SwapReport(total_mb=1024.0, used_mb=swap_mb, free_mb=0.0)
    rep.disk = DiskReport(mount="/System/Volumes/Data", size_gb=994.6,
                          used_gb=500.0, avail_gb=412.6, pct_used=55.0,
                          pct_free=41.5)
    rep.processes = ProcessReport(ghosts=[], total_ide_processes=7)
    rep.statedirs = StateDirReport(
        dirs=[StateDir(key="cursor-vscdb", path="/x", exists=True,
                       size_bytes=int(0.5e9))], total_bytes=int(3e9))
    return rep


class TestMetrics(unittest.TestCase):
    def test_record_and_series_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            metrics.record(_report("2026-07-29T10:00:00", 512.0), path=db)
            metrics.record(_report("2026-07-30T10:00:00", 1024.0), path=db)
            vals = metrics.series("swap.used_gb", days=7, path=db)
            self.assertEqual(len(vals), 2)
            self.assertAlmostEqual(vals[-1][1], 1.0)

    def test_rate_per_day(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            metrics.record(_report("2026-07-28T10:00:00", 0.0), path=db)
            metrics.record(_report("2026-07-30T10:00:00", 2048.0), path=db)
            rate = metrics.rate_per_day("swap.used_gb", days=7, path=db)
            self.assertIsNotNone(rate)
            self.assertAlmostEqual(rate, 1.0, places=5)  # 2 GB over 2 days

    def test_rate_needs_two_points(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            self.assertIsNone(metrics.rate_per_day("swap.used_gb", 7, path=db))
            metrics.record(_report("2026-07-30T10:00:00", 512.0), path=db)
            self.assertIsNone(metrics.rate_per_day("swap.used_gb", 7, path=db))

    def test_unavailable_sources_record_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            rep = make_empty_report("2026-07-30T10:00:00", 64.0)
            metrics.record(rep, path=db)  # everything unavailable/None
            self.assertEqual(metrics.series("smart.percent_used", 7, path=db), [])
            self.assertIsNone(metrics.latest("smart.percent_used", path=db))

    def test_apfs_error_records_no_snapshot_count(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            rep = _report("2026-07-30T10:00:00", 512.0)
            rep.apfs = ApfsReport(available=True,
                                  error="tmutil listlocalsnapshots failed",
                                  container_free_gb=412.6)
            metrics.record(rep, path=db)
            # error set → snapshot_count is the unmeasured default; no fake 0.0
            self.assertEqual(
                metrics.series("apfs.local_snapshot_count", 7, path=db), [])
            # container free came from diskutil, which succeeded
            self.assertEqual(
                metrics.latest("apfs.container_free_gb", path=db), 412.6)

    def test_record_never_raises_on_bad_path(self):
        rep = _report("2026-07-30T10:00:00", 512.0)
        metrics.record(rep, path=Path("/nonexistent-dir-x/m.db"))  # no raise

    def test_phase2_metrics_extract(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            rep = _report("2026-07-30T10:00:00", 512.0)
            rep.churn = models.ChurnReport(available=True, added=3, removed=2)
            rep.logs = models.LogsReport(available=True,
                                         total_bytes=int(2.5e9))
            rep.processes = models.ProcessReport(ide_procs=[
                models.GhostProcess(pid=7, ppid=1, name="Cursor",
                                    age_seconds=10, rss_mb=512.0)])
            metrics.record(rep, path=db)
            self.assertEqual(metrics.latest("churn.turnover", path=db), 5.0)
            self.assertEqual(metrics.latest("logs.total_gb", path=db), 2.5)
            self.assertEqual(metrics.latest("procs.rss.7", path=db), 512.0)


if __name__ == "__main__":
    unittest.main()
