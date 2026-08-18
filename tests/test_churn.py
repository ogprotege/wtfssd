from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wtfssd.collectors import churn


def _mk(home: Path, rel: str, size: int) -> None:
    p = home / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)


class TestChurn(unittest.TestCase):
    def test_first_run_stores_baseline_zero_turnover(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            state = home / "state.json"
            _mk(home, ".cursor/idx/a.pack", 100)
            rep = churn.collect_churn(home=home, state_path=state)
            self.assertTrue(rep.available)
            self.assertEqual(rep.note, "baseline stored")
            self.assertEqual(rep.added, 0)
            self.assertEqual(rep.pack_count, 1)
            self.assertTrue(state.exists())

    def test_turnover_detected(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            state = home / "state.json"
            _mk(home, ".cursor/idx/a.pack", 100)
            churn.collect_churn(home=home, state_path=state)
            (home / ".cursor/idx/a.pack").unlink()
            _mk(home, ".cursor/idx/b.pack", 200)
            _mk(home, "Library/Application Support/Cursor/CachedData/c.pack", 50)
            rep = churn.collect_churn(home=home, state_path=state)
            self.assertEqual(rep.added, 2)
            self.assertEqual(rep.removed, 1)
            self.assertEqual(rep.pack_bytes, 250)

    def test_no_watch_dirs_is_clean_zero(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            rep = churn.collect_churn(home=home, state_path=home / "s.json")
            self.assertTrue(rep.available)
            self.assertEqual(rep.pack_count, 0)

    def test_empty_object_baseline_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            state = home / "state.json"
            _mk(home, ".cursor/idx/a.pack", 100)
            state.write_text("{}")
            rep = churn.collect_churn(home=home, state_path=state)
            self.assertEqual(rep.added, 0)
            self.assertEqual(rep.note, "baseline stored")

    def test_corrupt_baseline_does_not_count_as_turnover(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            state = home / "state.json"
            _mk(home, ".cursor/idx/a.pack", 100)
            state.write_text("{not json")
            rep = churn.collect_churn(home=home, state_path=state)
            self.assertEqual(rep.added, 0)
            self.assertEqual(rep.removed, 0)
            self.assertEqual(rep.note, "baseline stored")


if __name__ == "__main__":
    unittest.main()
