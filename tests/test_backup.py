from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path

from ssdwtf.collectors import backup

FIX = Path(__file__).parent / "fixtures"
NOW = dt.datetime(2026, 7, 30, 12, 0, 0).timestamp()


def _runner_real(cmd):
    if "destinationinfo" in cmd:
        return (FIX / "tmutil_destinations.txt").read_text()
    if "latestbackup" in cmd:
        return (FIX / "tmutil_latestbackup.txt").read_text()  # mount failure
    return None


def _runner_healthy(cmd):
    if "destinationinfo" in cmd:
        return ("====================================================\n"
                "Name          : MOGD28TB\n"
                "Kind          : Local\n"
                "Mount Point   : /Volumes/MOGD28TB\n"
                "ID            : X\n")
    if "latestbackup" in cmd:
        return "/Volumes/MOGD28TB/Backups.backupdb/mac/2026-07-29-120000\n"
    return None


class TestBackup(unittest.TestCase):
    def test_parse_destinations(self):
        text = (FIX / "tmutil_destinations.txt").read_text()
        self.assertEqual(backup.parse_destinationinfo(text),
                         ["TM_05-31-26_to_0"])

    def test_parse_latest_date(self):
        self.assertEqual(
            backup.parse_latest_backup_date(
                "/Volumes/X/Backups.backupdb/m/2026-07-29-120000\n"),
            "2026-07-29-120000")
        self.assertIsNone(backup.parse_latest_backup_date(
            "Failed to mount backup destination, error: ..."))

    def test_collect_degraded_real_fixture(self):
        rep = backup.collect_backup(runner=_runner_real, now=NOW)
        self.assertTrue(rep.available)
        self.assertTrue(rep.configured)
        self.assertFalse(rep.destination_present)
        self.assertIsNone(rep.last_backup_age_hours)

    def test_collect_healthy(self):
        rep = backup.collect_backup(runner=_runner_healthy, now=NOW)
        self.assertTrue(rep.destination_present)
        self.assertAlmostEqual(rep.last_backup_age_hours, 24.0, places=1)

    def test_collect_not_configured(self):
        rep = backup.collect_backup(
            runner=lambda cmd: "" if "tmutil" in cmd else None, now=NOW)
        self.assertTrue(rep.available)
        self.assertFalse(rep.configured)

    def test_collect_degrades(self):
        rep = backup.collect_backup(runner=lambda cmd: None)
        self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
