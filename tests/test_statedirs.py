from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ssdwtf.collectors import statedirs


class TestDirSize(unittest.TestCase):
    def test_sums_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.bin").write_bytes(b"x" * 1000)
            sub = root / "sub"
            sub.mkdir()
            (sub / "b.bin").write_bytes(b"y" * 2000)
            self.assertEqual(statedirs.dir_size_bytes(root), 3000)

    def test_missing_dir_is_zero(self):
        self.assertEqual(statedirs.dir_size_bytes(Path("/nonexistent/xyz")), 0)


class TestCollect(unittest.TestCase):
    def test_collects_known_keys(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            vscdb = (home / "Library" / "Application Support" / "Cursor" /
                     "User" / "globalStorage")
            vscdb.mkdir(parents=True)
            (vscdb / "state.vscdb").write_bytes(b"z" * 5000)
            (vscdb / "state.vscdb.backup").write_bytes(b"z" * 4000)
            (home / ".claude").mkdir()
            (home / ".claude" / "f.json").write_bytes(b"q" * 100)
            rep = statedirs.collect_statedirs(home=home)
        by_key = {d.key: d for d in rep.dirs}
        self.assertEqual(by_key["cursor-vscdb"].size_bytes, 5000)
        self.assertTrue(by_key["cursor-vscdb"].exists)
        self.assertEqual(by_key["cursor-vscdb-backups"].size_bytes, 4000)
        self.assertEqual(by_key["claude-home"].size_bytes, 100)
        self.assertFalse(by_key["windsurf-app-support"].exists)
        self.assertEqual(rep.total_bytes, sum(d.size_bytes for d in rep.dirs))
        self.assertEqual(statedirs.vscdb_size_bytes(rep), 5000)

    def test_empty_home(self):
        with tempfile.TemporaryDirectory() as td:
            rep = statedirs.collect_statedirs(home=Path(td))
        self.assertEqual(rep.total_bytes, 0)
        self.assertTrue(all(not d.exists for d in rep.dirs))


if __name__ == "__main__":
    unittest.main()
