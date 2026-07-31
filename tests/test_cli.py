from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
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
        # 25 patches exceed the compiler's nested-block limit for a single
        # `with` statement, so contexts are stacked imperatively instead.
        with ExitStack() as stack:
            def _patch(*args, **kwargs):
                return stack.enter_context(mock.patch.object(*args, **kwargs))
            m_sd = _patch(cli.statedirs_col, "collect_statedirs")
            m_ap = _patch(cli.apfs_col, "collect_apfs")
            m_bu = _patch(cli.backup_col, "collect_backup")
            m_cr = _patch(cli.crashes_col, "collect_crashes")
            m_ch = _patch(cli.churn_col, "collect_churn")
            m_fd = _patch(cli.fds_col, "collect_fds")
            m_se = _patch(cli.secrets_col, "collect_secrets")
            m_lo = _patch(cli.logs_col, "collect_logs")
            m_gw = _patch(cli.gitwatch_col, "collect_gitwatch")
            m_re = _patch(cli.retention_col, "collect_retention")
            m_la = _patch(cli.launchd_col, "collect_launchd")
            m_sp = _patch(cli.spotlight_col, "collect_spotlight")
            m_mc = _patch(cli.mcp_col, "collect_mcp")
            m_sm = _patch(cli.smart_col, "collect_smart")
            _patch(cli.swap_col, "collect_swap", return_value=None)
            _patch(cli.disk_col, "collect_disk", return_value=None)
            m_pr = _patch(cli.proc_col, "collect_processes")
            m_prs = _patch(cli.pressure_col, "collect_pressure")
            m_sys = _patch(cli.system_col, "collect_system")
            m_wr = _patch(cli.writerate_col, "collect_writerate")
            _patch(cli, "host_ram_gb", return_value=64.0)
            _patch(cli.history, "append_history")
            _patch(cli.history, "load_history", return_value=[])
            _patch(cli.metrics, "record")
            stack.enter_context(redirect_stdout(io.StringIO()))
            m_sm.return_value = models.SmartReport(available=False, error="x")
            m_pr.return_value = models.ProcessReport()
            m_prs.return_value = models.PressureReport(available=False)
            m_sys.return_value = models.SystemReport(available=False)
            m_wr.return_value = models.WriteRateReport(available=False)
            m_re.return_value = models.RetentionReport(available=False)
            m_la.return_value = models.LaunchdReport(available=False)
            m_sp.return_value = models.SpotlightReport(available=False)
            m_mc.return_value = models.MCPReport(available=False)
            code = cli.main(["scan", "--fast", "--json"])
            self.assertIn(code, (0, 1, 2))
            m_sd.assert_not_called()
            m_ap.assert_not_called()
            m_bu.assert_not_called()
            m_cr.assert_not_called()
            m_ch.assert_not_called()
            m_fd.assert_not_called()
            m_se.assert_not_called()
            m_lo.assert_not_called()
            m_gw.assert_not_called()

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

    def test_digest_json_smoke(self):
        buf = io.StringIO()
        with mock.patch.object(cli, "_run_scan",
                               return_value=(fake_report(), [], 0)), \
             mock.patch.object(cli.metrics, "series", return_value=[]), \
             mock.patch.object(cli.metrics, "rate_per_day",
                               return_value=None), \
             mock.patch.object(cli.history, "load_history",
                               return_value=[]), \
             mock.patch.object(cli.history, "gb_written_per_day",
                               return_value=None), \
             redirect_stdout(buf):
            code = cli.main(["digest", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertIn("stats", data)


if __name__ == "__main__":
    unittest.main()
