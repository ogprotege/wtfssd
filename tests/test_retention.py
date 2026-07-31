from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ssdwtf.collectors import retention


class TestRetention(unittest.TestCase):
    def test_configured_and_absent(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cfg = home / ".claude/settings.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_text(json.dumps({"cleanupPeriodDays": 30}))
            rep = retention.collect_retention(home=home)
            self.assertTrue(rep.available)
            by_tool = {t.tool: t for t in rep.tools}
            self.assertEqual(by_tool["claude-code"].status, "configured")
            self.assertEqual(by_tool["claude-code"].value, 30)
            self.assertEqual(by_tool["cursor"].status, "absent")

    def test_invalid_json_counts_as_absent(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cfg = home / ".claude/settings.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_text("{not json")
            rep = retention.collect_retention(home=home)
            self.assertEqual(rep.tools[0].status, "absent")

    def test_empty_home_all_absent(self):
        with tempfile.TemporaryDirectory() as td:
            rep = retention.collect_retention(home=Path(td))
            self.assertTrue(all(t.status == "absent" for t in rep.tools))


if __name__ == "__main__":
    unittest.main()
