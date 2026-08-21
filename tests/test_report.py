from __future__ import annotations

import json
import unittest

from wtfssd import models, report


def sample() -> tuple[models.HealthReport, list[models.Finding]]:
    rep = models.HealthReport(
        timestamp="2026-07-30T10:53:07", host_ram_gb=64.0,
        smart=models.SmartReport(available=True, model="APPLE SSD AP1024Z",
                                 health="PASSED", percent_used=1,
                                 available_spare=100, media_errors=0,
                                 power_on_hours=243,
                                 data_units_written=25_531_425, tb_written=13.0),
        swap=models.SwapReport(total_mb=0.0, used_mb=0.0, free_mb=0.0, encrypted=True),
        disk=models.DiskReport(mount="/System/Volumes/Data", size_gb=926.0,
                               used_gb=519.0, avail_gb=386.0,
                               pct_used=58.0, pct_free=42.0),
        processes=models.ProcessReport(
            ghosts=[models.GhostProcess(9001, 1, "Cursor Helper", 27 * 86400, 4160.0)],
            total_ide_processes=29),
        statedirs=models.StateDirReport(
            dirs=[models.StateDir("claude-app-support", "/Users/b/…/Claude",
                                  True, 8_300_000_000, "Claude app state")],
            total_bytes=14_400_000_000),
    )
    findings = [models.Finding("monitor", "warn", "procs.ghosts",
                               "1 ghost IDE process", "oldest 27 days", "Cmd+Q Cursor")]
    return rep, findings


class TestReport(unittest.TestCase):
    def test_format_bytes(self):
        self.assertEqual(report.format_bytes(512), "512 B")
        self.assertEqual(report.format_bytes(1536), "1.5 KB")
        self.assertEqual(report.format_bytes(int(2.5e9)), "2.5 GB")
        self.assertEqual(report.format_bytes(int(54e12)), "54.0 TB")
        # .1f rounding must not print "1000.0 GB"
        self.assertEqual(report.format_bytes(int(999.96e9)), "1.0 TB")
        self.assertEqual(report.format_bytes(int(999.94e9)), "999.9 GB")

    def test_text_contains_sections(self):
        rep, findings = sample()
        text = report.render_text(rep, findings)
        for section in ("SSD / SMART", "STORAGE", "MEMORY", "PROCESSES",
                        "AGENTIC STATE", "FINDINGS", "Health:"):
            self.assertIn(section, text)
        self.assertIn("APPLE SSD AP1024Z", text)
        self.assertIn("13.0 TB", text)
        self.assertIn("27 days", text)
        self.assertIn("92/100", text)  # 1 warn → 92
        self.assertIn("(A)", text)

    def test_text_handles_unavailable(self):
        rep = models.make_empty_report("2026-07-30T10:53:07", 16.0)
        text = report.render_text(rep, [])
        self.assertIn("unavailable", text.lower())
        self.assertIn("100/100", text)

    def test_text_tier_skip_does_not_recommend_smartmontools(self):
        rep = models.make_empty_report("2026-07-30T10:53:07", 16.0)
        rep.scan_tier = "micro"
        rep.smart = models.SmartReport(
            available=False, error="not collected (tier=micro)")
        text = report.render_text(rep, [])
        self.assertIn("not collected (tier=micro)", text)
        self.assertNotIn("brew install smartmontools", text)
        self.assertNotIn("machine looks healthy", text)

    def test_text_shows_top_writers_when_available(self):
        rep, findings = sample()
        rep.writers = models.WritersReport(
            available=True,
            top=[models.WriterProc(
                pid=312, name="/System/Library/CoreServices/fileproviderd",
                written_bytes=76_300_000_000, elapsed_seconds=3 * 86400)],
            visible_total_bytes=80_000_000_000, process_count=5)
        text = report.render_text(rep, findings)
        self.assertIn("TOP DISK WRITERS", text)
        self.assertIn("fileproviderd", text)
        self.assertIn("76.3 GB", text)
        # the honest caveat: attribution only sees live processes
        self.assertIn("exited", text)

    def test_text_omits_writers_when_unavailable(self):
        rep, findings = sample()
        text = report.render_text(rep, findings)
        self.assertNotIn("TOP DISK WRITERS", text)

    def test_json_roundtrips(self):
        rep, findings = sample()
        data = json.loads(report.render_json(rep, findings))
        self.assertEqual(data["score"], 92)
        self.assertEqual(data["grade"], "A")
        self.assertEqual(data["report"]["smart"]["percent_used"], 1)
        self.assertEqual(data["findings"][0]["code"], "procs.ghosts")
        self.assertEqual(data["findings"][0]["evidence"], "measured")
        self.assertEqual(data["domains"]["processes"], "warn")
        self.assertEqual(data["domains"]["drive"], "ok")
        self.assertEqual(data["domains"]["backup"], "unknown")

    def test_history_table(self):
        rep, _ = sample()
        text = report.render_history([rep])
        self.assertIn("13.0", text)
        self.assertIn("2026-07-30", text)
        self.assertIn("TIMESTAMP", text.upper())
        self.assertIn("TIER", text.upper())

    def test_history_unmeasured_state_is_dash_not_zero(self):
        rep = models.make_empty_report("2026-08-02T12:00:00", 64.0)
        rep.scan_tier = "fast"
        rep.statedirs = models.StateDirReport(
            note="not collected (tier=fast)", total_bytes=0)
        rep.smart = models.SmartReport(available=False, error="not collected")
        rep.disk = models.DiskReport("/", 1000, 500, 412, 50, 50)
        rep.swap = models.SwapReport(0, 0, 0)
        text = report.render_history([rep])
        self.assertIn("—", text)
        self.assertNotRegex(text, r"\s0\.0\s*$")  # no trailing STATE 0.0
        self.assertIn("fast", text)
        self.assertIn("not measured", text.lower())

    def test_history_full_only_hides_fast_rows(self):
        full = models.make_empty_report("2026-08-02T12:00:00", 64.0)
        full.scan_tier = "full"
        full.statedirs = models.StateDirReport(total_bytes=20_000_000_000)
        full.smart = models.SmartReport(available=True, percent_used=1,
                                        tb_written=15.0)
        full.disk = models.DiskReport("/", 1000, 500, 400, 50, 50)
        full.swap = models.SwapReport(0, 0, 0)
        fast = models.make_empty_report("2026-08-02T12:05:00", 64.0)
        fast.scan_tier = "fast"
        fast.statedirs = models.StateDirReport(note="not collected (tier=fast)")
        text_all = report.render_history([full, fast])
        self.assertIn("fast", text_all)
        text_full = report.render_history([full, fast], full_only=True)
        self.assertNotIn("\n2026-08-02T12:05:00", text_full)
        self.assertIn("hid 1", text_full)
        self.assertIn("20.0", text_full)


class TestDomainTable(unittest.TestCase):
    def test_domain_table_marks_statuses(self):
        lines = report.domain_table({"drive": "ok", "backup": "critical"})
        joined = "\n".join(lines)
        self.assertIn("CRIT", joined)
        self.assertIn("backup", joined)


class TestDigest(unittest.TestCase):
    def test_render_digest_shape(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        out = report.render_digest(rep, [], {
            "days": 1, "scans": 5, "domains": {"drive": "ok"},
            "swap_used_gb": 1.5, "state_total_gb": 43.2,
            "backup_age_hours": 70.0})
        self.assertIn("digest", out)
        self.assertIn("1.5 GB", out)
        self.assertIn("43.2 GB", out)
        self.assertIn("health: 100/100", out)


if __name__ == "__main__":
    unittest.main()
