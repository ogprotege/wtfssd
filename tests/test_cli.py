from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest import mock

from wtfssd import cli, models
from wtfssd import config as config_mod


def fake_report() -> models.HealthReport:
    return models.make_empty_report("2026-07-30T10:53:07", 64.0)


def _patch_collectors_for_tier(stack, *, want_writerate=False, want_statedirs=False):
    """Patch collectors used by build_report so tests never shell out."""
    def _patch(*args, **kwargs):
        return stack.enter_context(mock.patch.object(*args, **kwargs))

    called = {"writerate": False, "statedirs": False, "writers": False}

    def wr(*a, **k):
        called["writerate"] = True
        return models.WriteRateReport(available=False, error="spy")

    def sd(*a, **k):
        called["statedirs"] = True
        return models.StateDirReport(note="spy")

    def wrs(*a, **k):
        called["writers"] = True
        return models.WritersReport(available=False, error="spy")

    _patch(cli.writerate_col, "collect_writerate", wr)
    _patch(cli.statedirs_col, "collect_statedirs", sd)
    _patch(cli.writers_col, "collect_writers", wrs)
    _patch(cli.swap_col, "collect_swap",
           return_value=models.SwapReport(0, 0, 0))
    _patch(cli.disk_col, "collect_disk",
           return_value=models.DiskReport("/", 100, 50, 50, 50, 50))
    _patch(cli.proc_col, "collect_processes",
           return_value=models.ProcessReport([], 0))
    _patch(cli.pressure_col, "collect_pressure",
           return_value=models.PressureReport(available=True, level=1))
    _patch(cli.smart_col, "collect_smart",
           return_value=models.SmartReport(available=False, error="spy"))
    _patch(cli.system_col, "collect_system",
           return_value=models.SystemReport(available=False, error="spy"))
    _patch(cli.backup_col, "collect_backup",
           return_value=models.BackupReport(available=False, error="spy"))
    _patch(cli.retention_col, "collect_retention",
           return_value=models.RetentionReport(available=False, error="spy"))
    _patch(cli.launchd_col, "collect_launchd",
           return_value=models.LaunchdReport(available=False, error="spy"))
    _patch(cli.spotlight_col, "collect_spotlight",
           return_value=models.SpotlightReport(available=False, error="spy"))
    _patch(cli.mcp_col, "collect_mcp",
           return_value=models.MCPReport(available=False, error="spy"))
    _patch(cli.apfs_col, "collect_apfs",
           return_value=models.ApfsReport(available=False, error="spy"))
    _patch(cli.crashes_col, "collect_crashes",
           return_value=models.CrashReport(available=False, error="spy"))
    _patch(cli.churn_col, "collect_churn",
           return_value=models.ChurnReport(available=False, error="spy"))
    _patch(cli.fds_col, "collect_fds",
           return_value=models.FdsReport(available=False, error="spy"))
    _patch(cli.secrets_col, "collect_secrets",
           return_value=models.SecretsReport(available=False, error="spy"))
    _patch(cli.logs_col, "collect_logs",
           return_value=models.LogsReport(available=False, error="spy"))
    _patch(cli.gitwatch_col, "collect_gitwatch",
           return_value=models.GitWatchReport(available=False, error="spy"))
    _patch(cli.smartext_col, "collect_smart_external",
           return_value=models.SmartReport(available=False, error="spy"))
    _patch(cli, "host_ram_gb", return_value=64.0)
    return called


class TestCli(unittest.TestCase):
    def _scan(self, argv, report, findings, tmp):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(cli, "build_report", return_value=report), \
             mock.patch("wtfssd.analyze.analyze", return_value=findings), \
             mock.patch("wtfssd.history.append_history"), \
             mock.patch("wtfssd.history.load_history", return_value=[]), \
             mock.patch("wtfssd.metrics.record"), \
             mock.patch("wtfssd.config.data_dir", return_value=Path(td)), \
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
            m_bu.return_value = models.BackupReport(available=False)
            code = cli.main(["scan", "--fast", "--json"])
            self.assertIn(code, (0, 1, 2))
            m_sd.assert_not_called()
            m_ap.assert_not_called()
            m_cr.assert_not_called()
            m_ch.assert_not_called()
            m_fd.assert_not_called()
            m_se.assert_not_called()
            m_lo.assert_not_called()
            m_gw.assert_not_called()
            m_wr.assert_not_called()

    def test_build_report_micro_does_not_call_writerate(self):
        config, _ = config_mod.load_config(path=Path("/nonexistent"))
        with ExitStack() as stack:
            called = _patch_collectors_for_tier(stack)
            cli.build_report(config, tier="micro")
        self.assertFalse(called["writerate"])
        self.assertFalse(called["statedirs"])

    def test_build_report_fast_does_not_call_writerate(self):
        config, _ = config_mod.load_config(path=Path("/nonexistent"))
        with ExitStack() as stack:
            called = _patch_collectors_for_tier(stack)
            cli.build_report(config, tier="fast")
        self.assertFalse(called["writerate"])
        self.assertFalse(called["statedirs"])

    def test_build_report_writers_only_on_full(self):
        config, _ = config_mod.load_config(path=Path("/nonexistent"))
        for tier, expected in (("micro", False), ("fast", False),
                               ("full", True)):
            with ExitStack() as stack:
                called = _patch_collectors_for_tier(stack)
                cli.build_report(config, tier=tier)
            self.assertEqual(called["writers"], expected, tier)

    def test_clean_dry_run_lists_targets(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch("wtfssd.cleaners.clean_target") as ct, \
             redirect_stdout(io.StringIO()) as buf:
            from wtfssd.cleaners import CleanResult, CleanAction
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
