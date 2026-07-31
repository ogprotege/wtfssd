from __future__ import annotations

import unittest

from ssdwtf import analyze, models
from ssdwtf.config import DEFAULTS


def base_report() -> models.HealthReport:
    rep = models.make_empty_report("2026-07-15T10:00:00", 16.0)
    rep.smart = models.SmartReport(
        available=True, model="APPLE SSD", health="PASSED", percent_used=2,
        available_spare=100, media_errors=0, power_on_hours=755,
        data_units_written=100_000_000, tb_written=54.0)
    rep.swap = models.SwapReport(total_mb=1024.0, used_mb=0.0, free_mb=1024.0)
    rep.disk = models.DiskReport(mount="/System/Volumes/Data", size_gb=460.0,
                                 used_gb=200.0, avail_gb=260.0,
                                 pct_used=43.5, pct_free=56.5)
    rep.processes = models.ProcessReport(ghosts=[], total_ide_processes=3)
    rep.statedirs = models.StateDirReport(dirs=[], total_bytes=1_000_000_000)
    return rep


def codes(findings):
    return {f.code for f in findings}


class TestAnalyze(unittest.TestCase):
    def test_healthy_machine_only_info(self):
        findings = analyze.analyze(base_report(), [], DEFAULTS)
        severities = {f.severity for f in findings}
        self.assertNotIn("warn", severities)
        self.assertNotIn("critical", severities)
        self.assertIn("smart.wear_info", codes(findings))

    def test_smart_criticals(self):
        rep = base_report()
        rep.smart.media_errors = 3
        rep.smart.available_spare = 80
        rep.smart.spare_threshold = 100  # device-threshold rule: 80 < 100 fires
        rep.smart.health = "FAILED!"
        findings = analyze.analyze(rep, [], DEFAULTS)
        got = codes(findings)
        self.assertIn("smart.media_errors", got)
        self.assertIn("smart.spare_low", got)
        self.assertIn("smart.health_failed", got)
        for f in findings:
            if f.code in ("smart.media_errors", "smart.spare_low",
                          "smart.health_failed"):
                self.assertEqual(f.severity, "critical")

    def test_smart_unavailable_is_info(self):
        rep = base_report()
        rep.smart = models.SmartReport(available=False, error="smartctl failed")
        findings = analyze.analyze(rep, [], DEFAULTS)
        self.assertIn("smart.unavailable", codes(findings))
        f = next(f for f in findings if f.code == "smart.unavailable")
        self.assertEqual(f.severity, "info")

    def test_swap_thresholds(self):
        rep = base_report()
        rep.swap.used_mb = 9 * 1024
        self.assertIn("swap.high", codes(analyze.analyze(rep, [], DEFAULTS)))
        rep.swap.used_mb = 17 * 1024
        findings = analyze.analyze(rep, [], DEFAULTS)
        self.assertIn("swap.critical", codes(findings))
        self.assertNotIn("swap.high", codes(findings))  # critical supersedes

    def test_disk_thresholds(self):
        rep = base_report()
        rep.disk.pct_free = 12.0
        self.assertIn("disk.low", codes(analyze.analyze(rep, [], DEFAULTS)))
        rep.disk.pct_free = 8.0
        findings = analyze.analyze(rep, [], DEFAULTS)
        self.assertIn("disk.critical", codes(findings))
        self.assertNotIn("disk.low", codes(findings))

    def test_ghost_processes(self):
        rep = base_report()
        rep.processes = models.ProcessReport(
            ghosts=[models.GhostProcess(pid=1, ppid=0, name="Cursor Helper",
                                        age_seconds=27 * 86400, rss_mb=4160.0)],
            total_ide_processes=29)
        findings = analyze.analyze(rep, [], DEFAULTS)
        got = codes(findings)
        self.assertIn("procs.ghosts", got)
        self.assertIn("procs.many", got)

    def test_state_thresholds(self):
        rep = base_report()
        rep.statedirs = models.StateDirReport(
            dirs=[models.StateDir(key="cursor-vscdb", path="/x/state.vscdb",
                                  exists=True, size_bytes=int(2.5e9))],
            total_bytes=int(25e9))
        got = codes(analyze.analyze(rep, [], DEFAULTS))
        self.assertIn("state.vscdb_large", got)
        self.assertIn("state.total_large", got)

    def test_write_rate_from_history(self):
        rep = base_report()
        h = []
        for i, ts in enumerate(["2026-07-13T10:00:00", "2026-07-14T10:00:00",
                                "2026-07-15T10:00:00"]):
            r = base_report()
            r.timestamp = ts
            r.smart.data_units_written = 100_000_000 + i * 800_000  # ~410 GB/day
            h.append(r)
        self.assertIn("smart.write_rate", codes(analyze.analyze(rep, h, DEFAULTS)))

    def test_monthly_check_on_first(self):
        rep = base_report()
        rep.timestamp = "2026-08-01T09:00:00"
        self.assertIn("smart.monthly_check", codes(analyze.analyze(rep, [], DEFAULTS)))

    def test_score_and_grade(self):
        self.assertEqual(analyze.health_score([]), 100)
        self.assertEqual(analyze.grade(100), "A")
        warns = [models.Finding("monitor", "warn", "x", "t", "d", "r")]
        crits = [models.Finding("monitor", "critical", "x", "t", "d", "r")]
        self.assertEqual(analyze.health_score(warns), 92)
        self.assertEqual(analyze.grade(92), "A")
        self.assertEqual(analyze.health_score(crits), 75)
        self.assertEqual(analyze.grade(75), "B")
        self.assertEqual(analyze.health_score(crits * 5), 0)
        self.assertEqual(analyze.grade(0), "F")


def _base_report() -> models.HealthReport:
    rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
    rep.swap = models.SwapReport(total_mb=1024.0, used_mb=0.0, free_mb=0.0)
    return rep


class TestPhase1Findings(unittest.TestCase):
    def _codes(self, rep, cfg=None):
        findings = analyze.analyze(rep, [], cfg or dict(DEFAULTS))
        return {f.code for f in findings}

    def test_backup_none_configured_is_critical(self):
        rep = _base_report()
        rep.backup = models.BackupReport(available=True, configured=False)
        codes = self._codes(rep)
        self.assertIn("backup.none_configured", codes)

    def test_backup_stale_warn_and_crit(self):
        rep = _base_report()
        rep.backup = models.BackupReport(available=True, configured=True,
                                         destination_present=True,
                                         last_backup_age_hours=72.0)
        self.assertIn("backup.stale", self._codes(rep))
        rep.backup = models.BackupReport(available=True, configured=True,
                                         destination_present=True,
                                         last_backup_age_hours=200.0)
        crit = [f for f in analyze.analyze(rep, [], dict(DEFAULTS))
                if f.code == "backup.stale"]
        self.assertEqual(crit[0].severity, "critical")

    def test_unavailable_backup_fires_nothing(self):
        rep = _base_report()  # backup defaults to available=False
        self.assertNotIn("backup.none_configured", self._codes(rep))

    def test_pressure_levels(self):
        rep = _base_report()
        rep.pressure = models.PressureReport(available=True, level=4)
        self.assertIn("pressure.critical", self._codes(rep))
        rep.pressure = models.PressureReport(available=True, level=2,
                                             free_pct=15.0)
        self.assertIn("pressure.warn", self._codes(rep))

    def test_spare_uses_device_threshold(self):
        rep = _base_report()
        rep.smart = models.SmartReport(available=True, health="PASSED",
                                       percent_used=2, available_spare=95,
                                       spare_threshold=10, media_errors=0)
        codes = self._codes(rep)
        self.assertNotIn("smart.spare_low", codes)  # 95 > 10: normal aging
        rep.smart = models.SmartReport(available=True, health="PASSED",
                                       percent_used=80, available_spare=8,
                                       spare_threshold=10, media_errors=0)
        self.assertIn("smart.spare_low", self._codes(rep))

    def test_critical_warning_bitmask(self):
        rep = _base_report()
        rep.smart = models.SmartReport(available=True, health="PASSED",
                                       critical_warning=2)
        self.assertIn("smart.critical_warning", self._codes(rep))

    def test_throttle_and_writerate(self):
        rep = _base_report()
        rep.system = models.SystemReport(available=True, cpu_speed_limit=62)
        self.assertIn("thermal.throttling", self._codes(rep))
        rep = _base_report()
        rep.writerate = models.WriteRateReport(available=True, mb_per_s=450.0)
        self.assertIn("writerate.storm", self._codes(rep))

    def test_crashes_frequent(self):
        rep = _base_report()
        rep.crashes = models.CrashReport(available=True,
                                         weekly={"Cursor": 5}, total_weekly=5)
        self.assertIn("crashes.frequent", self._codes(rep))

    def test_external_unhealthy(self):
        rep = _base_report()
        rep.external_smart = [models.SmartReport(available=True,
                                                 health="FAILED!")]
        self.assertIn("smart.external_unhealthy", self._codes(rep))

    def test_domain_statuses(self):
        rep = _base_report()
        rep.backup = models.BackupReport(available=True, configured=False)
        findings = analyze.analyze(rep, [], dict(DEFAULTS))
        dom = analyze.domain_statuses(findings, rep)
        self.assertEqual(dom["backup"], "critical")
        self.assertEqual(set(dom), set(analyze.DOMAINS))
        # drive collector unavailable in _base_report → unknown (no findings)
        self.assertEqual(dom["drive"], "unknown")

    def test_hint_findings_carry_inferred_evidence(self):
        rep = _base_report()
        rep.swap = models.SwapReport(total_mb=16384.0, used_mb=9 * 1024,
                                     free_mb=0.0)
        rep.pressure = models.PressureReport(available=True, level=2,
                                             free_pct=15.0)
        rep.system = models.SystemReport(available=True, uptime_days=20.0)
        history = []
        for i, ts in enumerate(["2026-07-28T10:00:00", "2026-07-29T10:00:00",
                                "2026-07-30T10:00:00"]):
            h = _base_report()
            h.timestamp = ts
            h.swap = models.SwapReport(total_mb=16384.0,
                                       used_mb=(6 + i) * 1024, free_mb=0.0)
            history.append(h)
        findings = analyze.analyze(rep, history, dict(DEFAULTS))
        ev = {f.code: f.evidence for f in findings}
        self.assertEqual(ev["memory.thrash_hint"], "inferred")
        self.assertEqual(ev["uptime.restart_hint"], "inferred")


if __name__ == "__main__":
    unittest.main()
