from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ssdwtf.collectors import mcp

CONFIG = {"mcpServers": {
    "firecrawl": {"command": "node", "args": ["/opt/fc/dist/index.js"]},
    "x-api": {"command": "/usr/bin/python3", "args": ["server.py"]},
}}

PS = """  PID ELAPSED     RSS ARGS
  501 02:00:00  310272 node /opt/fc/dist/index.js
  502 5-00:00:00  10240 /usr/bin/python3 server.py
  503 01:00:00 9999999 /Applications/Claude.app/Contents/MacOS/Claude --flag
  504 00:30:00    5120 /usr/sbin/sshd
"""

CONFIG_NPX = {"mcpServers": {
    "firecrawl": {"command": "npx", "args": ["-y", "firecrawl-mcp"]},
    "mytool": {"command": "/usr/local/bin/mytool", "args": ["serve"]},
}}

PS_NPX = """  PID ELAPSED     RSS ARGS
  601 02:00:00  310272 npx -y firecrawl-mcp
  602 01:00:00  204800 npx something-else
  603 03:00:00   51200 /usr/local/bin/mytool serve --port 9
"""


class TestMcp(unittest.TestCase):
    def _config_file(self, td: str) -> Path:
        p = Path(td) / "cfg.json"
        p.write_text(json.dumps(CONFIG))
        return p

    def test_parse_config(self):
        got = mcp.parse_mcp_config(json.dumps(CONFIG))
        self.assertEqual(got["firecrawl"], "node /opt/fc/dist/index.js")
        self.assertEqual(mcp.parse_mcp_config("not json"), {})
        self.assertEqual(mcp.parse_mcp_config("{}"), {})

    def test_collect_live_servers(self):
        with tempfile.TemporaryDirectory() as td:
            rep = mcp.collect_mcp(config_path=self._config_file(td),
                                  runner=lambda cmd: PS, home=Path(td))
            self.assertTrue(rep.available)
            self.assertTrue(rep.claude_running)
            by_name = {s.name: s for s in rep.servers}
            self.assertEqual(by_name["firecrawl"].live_pids, 1)
            self.assertAlmostEqual(by_name["firecrawl"].rss_mb, 303.0, places=0)
            self.assertEqual(by_name["x-api"].oldest_age_s, 5 * 86400)

    def test_collect_missing_config_degrades(self):
        rep = mcp.collect_mcp(config_path=Path("/nonexistent-x.json"),
                              runner=lambda cmd: PS)
        self.assertFalse(rep.available)

    def test_collect_ps_failure_degrades(self):
        with tempfile.TemporaryDirectory() as td:
            rep = mcp.collect_mcp(config_path=self._config_file(td),
                                  runner=lambda cmd: None, home=Path(td))
            self.assertFalse(rep.available)

    def test_npx_server_matches_full_command_only(self):
        # a generic interpreter (npx) must not match every npx process —
        # only the one whose args contain the full declared command string
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cfg.json"
            p.write_text(json.dumps(CONFIG_NPX))
            rep = mcp.collect_mcp(config_path=p, runner=lambda cmd: PS_NPX,
                                  home=Path(td))
        self.assertTrue(rep.available)
        by_name = {s.name: s for s in rep.servers}
        self.assertEqual(by_name["firecrawl"].live_pids, 1)
        self.assertAlmostEqual(by_name["firecrawl"].rss_mb, 303.0, places=0)
        # non-interpreter commands still match on the basename
        self.assertEqual(by_name["mytool"].live_pids, 1)


if __name__ == "__main__":
    unittest.main()
