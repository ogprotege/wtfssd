from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ssdwtf import config


class TestConfig(unittest.TestCase):
    def test_defaults_when_missing(self):
        cfg, warn = config.load_config(Path("/nonexistent/ssdwtf/config.json"))
        self.assertIsNone(warn)
        self.assertEqual(cfg["swap"]["warn_gb"], 8.0)
        self.assertEqual(cfg["disk"]["mount"], "/System/Volumes/Data")

    def test_deep_merge_user_override(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.json"
            p.write_text(json.dumps({"swap": {"warn_gb": 4.0}}))
            cfg, warn = config.load_config(p)
        self.assertIsNone(warn)
        self.assertEqual(cfg["swap"]["warn_gb"], 4.0)      # overridden
        self.assertEqual(cfg["swap"]["crit_gb"], 16.0)     # default kept
        self.assertEqual(cfg["alerts"]["cooldown_hours"], 24.0)

    def test_invalid_json_uses_defaults_with_warning(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.json"
            p.write_text("{not json")
            cfg, warn = config.load_config(p)
        self.assertIsNotNone(warn)
        self.assertEqual(cfg["procs"]["ghost_days"], 3.0)

    def test_defaults_not_mutated_by_merge(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.json"
            p.write_text(json.dumps({"swap": {"warn_gb": 1.0}}))
            config.load_config(p)
        self.assertEqual(config.DEFAULTS["swap"]["warn_gb"], 8.0)


if __name__ == "__main__":
    unittest.main()
