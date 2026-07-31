from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN = (Path(__file__).parent.parent / "contrib" / "swiftbar"
          / "ssdwtf.5m.py")

PAYLOAD = {
    "score": 68, "grade": "C",
    "domains": {"drive": "ok", "backup": "critical", "memory": "ok",
                "work": "unknown"},
    "findings": [
        {"severity": "critical", "code": "backup.stale",
         "title": "Last successful backup 9 days ago"},
        {"severity": "info", "code": "smart.wear_info", "title": "wear 2%"},
    ],
}


class TestSwiftBar(unittest.TestCase):
    def _run(self, payload=PAYLOAD):
        env = dict(os.environ, SSDWTF_JSON=json.dumps(payload))
        return subprocess.run([sys.executable, str(PLUGIN)],
                              capture_output=True, text=True, env=env,
                              timeout=30)

    def test_renders_title_colored_by_worst(self):
        out = self._run().stdout
        self.assertTrue(out.startswith("SSD:C | color=red"))
        self.assertIn("Health 68/100 (C)", out)
        self.assertIn("🔴 backup", out)
        self.assertIn("[CRITICAL] Last successful backup 9 days ago", out)
        self.assertIn("Refresh | refresh=true", out)

    def test_clean_payload_is_green(self):
        out = self._run({"score": 100, "grade": "A", "domains": {},
                         "findings": []}).stdout
        self.assertTrue(out.startswith("SSD:A | color=green"))

    def test_bad_payload_degrades_to_gray(self):
        env = dict(os.environ, SSDWTF_JSON="{not json")
        out = subprocess.run([sys.executable, str(PLUGIN)],
                             capture_output=True, text=True, env=env,
                             timeout=30)
        self.assertEqual(out.returncode, 0)
        self.assertTrue(out.stdout.startswith("SSD:? | color=gray"))


if __name__ == "__main__":
    unittest.main()
