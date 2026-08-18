from __future__ import annotations

import unittest

from wtfssd import models
from wtfssd.collectors import writers

# Captured shape of `ps -axo pid=,etime=,comm=` (no header with = suffixes).
PS = (
    "  312 03-20:57:51 /System/Library/CoreServices/fileproviderd\n"
    "  845       08:29 /Applications/Claude.app/Contents/MacOS/Claude\n"
    " 1200       27:15 /Applications/Utilities/Terminal.app/Contents/MacOS/Terminal\n"
    " 1300       01:00 /usr/sbin/idle-no-writes\n"
    "garbage line-without-pid\n"
)

RUSAGE = {312: 76_300_000_000, 845: 11_000_000_000,
          1200: 900_000_000, 1300: 0}


def fake_runner(cmd, **kwargs):
    assert cmd[0] == "ps"
    return PS


class TestWritersCollector(unittest.TestCase):
    def test_collects_and_ranks_visible_writers(self):
        rep = writers.collect_writers(top_n=2, runner=fake_runner,
                                      rusage_fn=RUSAGE.get)
        self.assertTrue(rep.available)
        self.assertEqual([w.pid for w in rep.top], [312, 845])  # bytes desc
        self.assertEqual(rep.top[0].written_bytes, 76_300_000_000)
        self.assertEqual(rep.top[0].name,
                         "/System/Library/CoreServices/fileproviderd")
        self.assertEqual(rep.top[0].elapsed_seconds,
                         3 * 86400 + 20 * 3600 + 57 * 60 + 51)
        self.assertEqual(rep.top[1].elapsed_seconds, 8 * 60 + 29)
        # zero-write pid excluded; totals cover ALL visible writers, not
        # only the top-N slice
        self.assertEqual(rep.process_count, 3)
        self.assertEqual(rep.visible_total_bytes,
                         76_300_000_000 + 11_000_000_000 + 900_000_000)

    def test_ps_failure_degrades(self):
        rep = writers.collect_writers(runner=lambda cmd, **k: None,
                                      rusage_fn=RUSAGE.get)
        self.assertFalse(rep.available)
        self.assertIn("ps", rep.error)

    def test_rusage_denied_or_raising_pids_are_skipped(self):
        def rusage(pid):
            if pid == 312:
                raise OSError("denied")
            return RUSAGE.get(pid)
        rep = writers.collect_writers(runner=fake_runner, rusage_fn=rusage)
        self.assertTrue(rep.available)
        self.assertEqual([w.pid for w in rep.top], [845, 1200])

    def test_roundtrip_through_history_dicts(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        rep.writers = models.WritersReport(
            available=True,
            top=[models.WriterProc(pid=1, name="/bin/x", written_bytes=5,
                                   elapsed_seconds=60)],
            visible_total_bytes=5, process_count=1)
        loaded = models.report_from_dict(models.report_to_dict(rep))
        self.assertTrue(loaded.writers.available)
        self.assertEqual(loaded.writers.top[0].written_bytes, 5)

    def test_legacy_history_rows_have_no_writers(self):
        d = models.report_to_dict(
            models.make_empty_report("2026-07-30T10:00:00", 64.0))
        del d["writers"]
        loaded = models.report_from_dict(d)
        self.assertFalse(loaded.writers.available)


if __name__ == "__main__":
    unittest.main()
