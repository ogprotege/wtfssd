from __future__ import annotations

import json
import unittest

from ssdwtf import models, report


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


class TestDomainTable(unittest.TestCase):
    def test_domain_table_marks_statuses(self):
        lines = report.domain_table({"drive": "ok", "backup": "critical"})
        joined = "\n".join(lines)
        self.assertIn("CRIT", joined)
        self.assertIn("backup", joined)


if __name__ == "__main__":
    unittest.main()
