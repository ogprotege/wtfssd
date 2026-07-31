from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from wtfssd.collectors import secrets


class TestSecrets(unittest.TestCase):
    def test_disabled_is_inert(self):
        rep = secrets.collect_secrets(enabled=False, home=Path("/nope"))
        self.assertTrue(rep.available)
        self.assertFalse(rep.enabled)
        self.assertEqual(rep.matches, [])

    def test_scan_text_finds_rules_without_values(self):
        matches: list = []
        rules = tuple((n, __import__("re").compile(p)) for n, p in secrets.RULES)
        fake_aws = "AKIA" + "X" * 16  # built at runtime: no literal key in source
        secrets.scan_text("/f", '{"key": "' + fake_aws + '"}\nplain',
                          rules, matches)
        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual((m.path, m.line, m.rule), ("/f", 1, "aws-access-key"))
        self.assertNotIn(fake_aws, str(m))

    def test_collect_scans_claude_config(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cfg = home / "Library/Application Support/Claude/claude_desktop_config.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_text('{"mcpServers": {"x": {"env": '
                           '{"KEY": "ghp_aaaaaaaaaaaaaaaaaaaaaa"}}}}')
            rep = secrets.collect_secrets(enabled=True, home=home)
            self.assertTrue(rep.enabled)
            self.assertEqual(len(rep.matches), 1)
            self.assertEqual(rep.matches[0].rule, "github-token")

    def test_collect_scans_vscdb(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            db = home / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
            db.parent.mkdir(parents=True)
            conn = sqlite3.connect(str(db))
            conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
            conn.execute("INSERT INTO ItemTable VALUES ('k', ?)",
                         ("token = sk-ant-" + "a" * 30,))
            conn.commit(); conn.close()
            rep = secrets.collect_secrets(enabled=True, home=home)
            self.assertEqual(len(rep.matches), 1)
            self.assertEqual(rep.matches[0].rule, "anthropic-key")

    def test_oversized_files_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cfg = home / "Library/Application Support/Claude/claude_desktop_config.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_bytes(b'{"x": "' + b"AKIA" + b"X" * 16 + b'"}' + b" " * (6 * 1024 * 1024))
            rep = secrets.collect_secrets(enabled=True, home=home)
            self.assertEqual(rep.matches, [])


if __name__ == "__main__":
    unittest.main()
