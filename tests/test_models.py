from __future__ import annotations

import unittest

from ssdwtf import models


def sample_report() -> models.HealthReport:
    return models.HealthReport(
        timestamp="2026-07-30T10:53:07",
        host_ram_gb=64.0,
        smart=models.SmartReport(
            available=True, model="APPLE SSD AP1024Z", health="PASSED",
            percent_used=1, available_spare=100, media_errors=0,
            power_on_hours=243, data_units_written=25531425, tb_written=13.0,
        ),
        swap=models.SwapReport(total_mb=1024.0, used_mb=512.0, free_mb=512.0, encrypted=True),
        disk=models.DiskReport(mount="/System/Volumes/Data", size_gb=926.0,
                               used_gb=519.0, avail_gb=386.0, pct_used=58.0, pct_free=42.0),
        processes=models.ProcessReport(
            ghosts=[models.GhostProcess(pid=1, ppid=0, name="Cursor Helper",
                                        age_seconds=2_332_800, rss_mb=4160.0)],
            total_ide_processes=29,
        ),
        statedirs=models.StateDirReport(
            dirs=[models.StateDir(key="cursor-vscdb",
                                  path="/Users/x/state.vscdb",
                                  exists=True, size_bytes=300_000_000,
                                  note="chat database")],
            total_bytes=300_000_000,
        ),
    )


class TestModels(unittest.TestCase):
    def test_roundtrip(self):
        rep = sample_report()
        d = models.report_to_dict(rep)
        rep2 = models.report_from_dict(d)
        self.assertEqual(rep, rep2)

    def test_roundtrip_with_none_optionals(self):
        rep = sample_report()
        rep.swap = None
        rep.disk = None
        rep2 = models.report_from_dict(models.report_to_dict(rep))
        self.assertEqual(rep, rep2)
        self.assertIsNone(rep2.swap)
        self.assertIsNone(rep2.disk)

    def test_empty_report(self):
        rep = models.make_empty_report("2026-07-30T00:00:00", 16.0)
        self.assertFalse(rep.smart.available)
        self.assertEqual(rep.statedirs.dirs, [])
        d = models.report_to_dict(rep)
        self.assertEqual(models.report_from_dict(d), rep)


if __name__ == "__main__":
    unittest.main()
