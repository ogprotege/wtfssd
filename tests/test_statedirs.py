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
        # Double-count guard: entries nested inside another tracked entry
        # (cursor-vscdb, cursor-vscdb-backups live inside cursor-app-support)
        # are reported individually but excluded from total_bytes.
        non_nested = [d for d in rep.dirs
                      if d.exists and not any(
                          o is not d and d.path.startswith(o.path + "/")
                          for o in rep.dirs)]
        self.assertEqual(rep.total_bytes, sum(d.size_bytes for d in non_nested))
        self.assertEqual(statedirs.vscdb_size_bytes(rep), 5000)

    def test_empty_home(self):
        with tempfile.TemporaryDirectory() as td:
            rep = statedirs.collect_statedirs(home=Path(td))
        self.assertEqual(rep.total_bytes, 0)
        self.assertTrue(all(not d.exists for d in rep.dirs))

    def test_categories_and_double_count_guard(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            app = home / "Library/Application Support/Cursor"
            (app / "User/globalStorage").mkdir(parents=True)
            (app / "blob.bin").write_bytes(b"x" * 1000)
            (app / "User/globalStorage/state.vscdb").write_bytes(b"y" * 500)
            rep = statedirs.collect_statedirs(home=home)
            by_key = {d.key: d for d in rep.dirs}
            self.assertEqual(by_key["cursor-app-support"].category, "ai-state")
            # total counts cursor-app-support (1500) but NOT cursor-vscdb
            # (nested) — no double count
            self.assertEqual(rep.total_bytes, 1500)
            self.assertEqual(rep.category_totals.get("ai-state"), 1500)
            # vscdb is still reported individually
            self.assertEqual(by_key["cursor-vscdb"].size_bytes, 500)


if __name__ == "__main__":
    unittest.main()
