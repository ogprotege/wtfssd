from __future__ import annotations

import unittest

from wtfssd import models


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


class TestPhase1Models(unittest.TestCase):
    def test_new_reports_have_defaults(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        self.assertFalse(rep.pressure.available)
        self.assertFalse(rep.system.available)
        self.assertFalse(rep.apfs.available)
        self.assertFalse(rep.backup.available)
        self.assertFalse(rep.crashes.available)
        self.assertFalse(rep.writerate.available)
        self.assertEqual(rep.external_smart, [])

    def test_finding_evidence_defaults_measured(self):
        f = models.Finding(pillar="monitor", severity="info", code="x.y",
                           title="t", detail="d", recommendation="r")
        self.assertEqual(f.evidence, "measured")

    def test_smart_new_fields_default_none(self):
        s = models.SmartReport(available=True)
        self.assertIsNone(s.critical_warning)
        self.assertIsNone(s.spare_threshold)
        self.assertIsNone(s.unsafe_shutdowns)
        self.assertIsNone(s.temperature_c)

    def test_roundtrip_with_new_fields(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        rep.pressure = models.PressureReport(available=True, level=1, free_pct=70.0)
        rep.backup = models.BackupReport(available=True, configured=True,
                                         destination_present=False,
                                         last_backup_age_hours=None,
                                         destinations=["TM Backup"])
        d = models.report_to_dict(rep)
        back = models.report_from_dict(d)
        self.assertEqual(back.pressure.level, 1)
        self.assertTrue(back.backup.configured)
        self.assertEqual(back.backup.destinations, ["TM Backup"])

    def test_from_dict_tolerates_old_rows(self):
        # a v0.1.0 history row: no phase-1 keys at all
        rep = models.make_empty_report("2026-07-29T10:00:00", 64.0)
        d = models.report_to_dict(rep)
        for k in ("pressure", "system", "apfs", "backup", "crashes",
                  "writerate", "external_smart"):
            d.pop(k, None)
        back = models.report_from_dict(d)
        self.assertFalse(back.pressure.available)
        self.assertEqual(back.external_smart, [])


class TestPhase2Models(unittest.TestCase):
    def test_new_reports_default_unavailable(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        for name in ("churn", "fds", "mcp", "secrets", "retention",
                     "launchd", "spotlight", "logs", "gitwatch"):
            self.assertFalse(getattr(rep, name).available, name)

    def test_statedir_category_and_totals_default(self):
        sd = models.StateDir(key="k", path="/x", exists=True, size_bytes=1)
        self.assertEqual(sd.category, "")
        self.assertEqual(models.StateDirReport().category_totals, {})

    def test_process_report_ide_procs_default(self):
        self.assertEqual(models.ProcessReport().ide_procs, [])

    def test_roundtrip_nested_phase2(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        rep.mcp = models.MCPReport(
            available=True, claude_running=True,
            servers=[models.MCPServer(name="firecrawl", command="node fc.js",
                                      live_pids=2, rss_mb=310.5)])
        rep.gitwatch = models.GitWatchReport(
            available=True,
            repos=[models.RepoStatus(path="/repo", uncommitted=3,
                                     has_remote=False, unpushed=7)])
        rep.secrets = models.SecretsReport(
            available=True, enabled=True,
            matches=[models.SecretMatch(path="/f", line=9, rule="aws-access-key")])
        back = models.report_from_dict(models.report_to_dict(rep))
        self.assertEqual(back.mcp.servers[0].name, "firecrawl")
        self.assertEqual(back.gitwatch.repos[0].unpushed, 7)
        self.assertEqual(back.secrets.matches[0].rule, "aws-access-key")

    def test_from_dict_tolerates_phase1_rows(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        d = models.report_to_dict(rep)
        for k in ("churn", "fds", "mcp", "secrets", "retention",
                  "launchd", "spotlight", "logs", "gitwatch"):
            d.pop(k, None)
        back = models.report_from_dict(d)
        self.assertFalse(back.mcp.available)


if __name__ == "__main__":
    unittest.main()
