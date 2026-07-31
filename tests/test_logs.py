from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ssdwtf.collectors import logs


class TestLogs(unittest.TestCase):
    def test_sizes_and_top(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            big = home / "Library/Logs/Cursor"
            big.mkdir(parents=True)
            (big / "big.log").write_bytes(b"x" * 3000)
            small = home / "Library/Logs/Other"
            small.mkdir(parents=True)
            (small / "s.log").write_bytes(b"y" * 100)
            extra = home / "mcps/firecrawl"
            extra.mkdir(parents=True)
            (extra / "e.log").write_bytes(b"z" * 500)
            rep = logs.collect_logs(home=home, extra_dirs=("mcps/firecrawl",))
            self.assertTrue(rep.available)
            self.assertEqual(rep.total_bytes, 3600)
            self.assertEqual(rep.top[0].key, "logs/Cursor")
            self.assertIn("mcps/firecrawl", {e.key for e in rep.top})

    def test_missing_logs_dir_is_zero(self):
        with tempfile.TemporaryDirectory() as td:
            rep = logs.collect_logs(home=Path(td))
            self.assertTrue(rep.available)
            self.assertEqual(rep.total_bytes, 0)


if __name__ == "__main__":
    unittest.main()
