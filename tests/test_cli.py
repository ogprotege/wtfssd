from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from ssdwtf import cli, models


def fake_report() -> models.HealthReport:
    return models.make_empty_report("2026-07-30T10:53:07", 64.0)


class TestCli(unittest.TestCase):
    def _scan(self, argv, report, findings, tmp):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(cli, "build_report", return_value=report), \
             mock.patch("ssdwtf.analyze.analyze", return_value=findings), \
             mock.patch("ssdwtf.history.append_history"), \
             mock.patch("ssdwtf.history.load_history", return_value=[]), \
             mock.patch("ssdwtf.metrics.record"), \
             mock.patch("ssdwtf.config.data_dir", return_value=Path(td)), \
             redirect_stdout(buf):
            code = cli.main(argv)
        return code, buf.getvalue()

    def test_scan_json_exit0(self):
        code, out = self._scan(["scan", "--json"], fake_report(), [], None)
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["score"], 100)

    def test_scan_warn_exit1_critical_exit2(self):
        warn = models.Finding("monitor", "warn", "x", "t", "d", "r")
        crit = models.Finding("monitor", "critical", "y", "t", "d", "r")
        code, _ = self._scan(["scan"], fake_report(), [warn], None)
        self.assertEqual(code, 1)
        code, _ = self._scan(["scan"], fake_report(), [warn, crit], None)
        self.assertEqual(code, 2)

    def test_scan_fast_skips_slow_collectors(self):
        with mock.patch.object(cli.statedirs_col, "collect_statedirs") as m_sd, \
             mock.patch.object(cli.apfs_col, "collect_apfs") as m_ap, \
             mock.patch.object(cli.backup_col, "collect_backup") as m_bu, \
             mock.patch.object(cli.crashes_col, "collect_crashes") as m_cr, \
             mock.patch.object(cli.smart_col, "collect_smart") as m_sm, \
             mock.patch.object(cli.swap_col, "collect_swap", return_value=None), \
             mock.patch.object(cli.disk_col, "collect_disk", return_value=None), \
             mock.patch.object(cli.proc_col, "collect_processes") as m_pr, \
             mock.patch.object(cli.pressure_col, "collect_pressure") as m_prs, \
             mock.patch.object(cli.system_col, "collect_system") as m_sys, \
             mock.patch.object(cli.writerate_col, "collect_writerate") as m_wr, \
             mock.patch.object(cli, "host_ram_gb", return_value=64.0), \
             mock.patch.object(cli.history, "append_history"), \
             mock.patch.object(cli.history, "load_history", return_value=[]), \
             mock.patch.object(cli.metrics, "record"), \
             redirect_stdout(io.StringIO()):
            m_sm.return_value = models.SmartReport(available=False, error="x")
            m_pr.return_value = models.ProcessReport()
            m_prs.return_value = models.PressureReport(available=False)
            m_sys.return_value = models.SystemReport(available=False)
            m_wr.return_value = models.WriteRateReport(available=False)
            code = cli.main(["scan", "--fast", "--json"])
            self.assertIn(code, (0, 1, 2))
            m_sd.assert_not_called()
            m_ap.assert_not_called()
            m_bu.assert_not_called()
            m_cr.assert_not_called()

    def test_clean_dry_run_lists_targets(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch("ssdwtf.cleaners.clean_target") as ct, \
             redirect_stdout(io.StringIO()) as buf:
            from ssdwtf.cleaners import CleanResult, CleanAction
            ct.return_value = CleanResult("cursor-caches", False, actions=[
                CleanAction("/x/Cache", 500, "would-trash")])
            code = cli.main(["clean", "cursor-caches"])
        self.assertEqual(code, 0)
        self.assertIn("would-trash", buf.getvalue())
        self.assertIn("500", buf.getvalue())

    def test_clean_unknown_target_exit3(self):
        with redirect_stdout(io.StringIO()):
            code = cli.main(["clean", "nope"])
        self.assertEqual(code, 3)

    def test_config_show(self):
        with redirect_stdout(io.StringIO()) as buf:
            code = cli.main(["config", "--show"])
        self.assertEqual(code, 0)
        self.assertIn("warn_gb", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
