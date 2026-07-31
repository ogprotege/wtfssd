from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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

    def test_nondict_payload_degrades_to_gray(self):
        env = dict(os.environ, SSDWTF_JSON="[1,2]")
        out = subprocess.run([sys.executable, str(PLUGIN)],
                             capture_output=True, text=True, env=env,
                             timeout=30)
        self.assertEqual(out.returncode, 0)
        self.assertTrue(out.stdout.startswith("SSD:? | color=gray"))

    def test_nondict_finding_entry_is_skipped(self):
        payload = dict(PAYLOAD,
                       findings=["oops", 42, *PAYLOAD["findings"]])
        out = self._run(payload)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stderr, "")
        self.assertTrue(out.stdout.startswith("SSD:C | color=red"))
        self.assertIn("[CRITICAL] Last successful backup 9 days ago",
                      out.stdout)

    def test_scan_action_falls_back_without_ssdwtf_on_path(self):
        with tempfile.TemporaryDirectory() as empty_path:
            env = dict(os.environ, SSDWTF_JSON=json.dumps(PAYLOAD),
                       PATH=empty_path)
            out = subprocess.run([sys.executable, str(PLUGIN)],
                                 capture_output=True, text=True, env=env,
                                 timeout=30)
        self.assertEqual(out.returncode, 0)
        line = next(l for l in out.stdout.splitlines()
                    if "Run full scan" in l)
        self.assertNotIn("bash=ssdwtf ", line)
        self.assertIn("terminal=true", line)

    def test_scan_action_prefers_installed_ssdwtf(self):
        with tempfile.TemporaryDirectory() as bin_dir:
            fake = Path(bin_dir) / "ssdwtf"
            fake.write_text("#!/bin/sh\nexit 0\n")
            fake.chmod(0o755)
            env = dict(os.environ, SSDWTF_JSON=json.dumps(PAYLOAD),
                       PATH=bin_dir)
            out = subprocess.run([sys.executable, str(PLUGIN)],
                                 capture_output=True, text=True, env=env,
                                 timeout=30)
        self.assertIn(
            "Run full scan | bash=ssdwtf param1=scan terminal=true",
            out.stdout)


if __name__ == "__main__":
    unittest.main()
