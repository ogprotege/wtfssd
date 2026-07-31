from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wtfssd.collectors import launchd


def _mk(d: Path, name: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("<plist/>")


class TestLaunchd(unittest.TestCase):
    def test_first_run_stores_baseline_no_findings(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            _mk(home / "Library/LaunchAgents", "com.a.plist")
            rep = launchd.collect_launchd(home=home,
                                          state_path=home / "b.json",
                                          system_dirs=())
            self.assertTrue(rep.available)
            self.assertFalse(rep.baseline_exists)
            self.assertEqual(rep.new_since_baseline, [])
            self.assertEqual(rep.agent_count, 1)

    def test_new_agent_detected_once(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            agents = home / "Library/LaunchAgents"
            _mk(agents, "com.a.plist")
            state = home / "b.json"
            launchd.collect_launchd(home=home, state_path=state, system_dirs=())
            _mk(agents, "com.evil.plist")
            rep = launchd.collect_launchd(home=home, state_path=state,
                                          system_dirs=())
            self.assertEqual(rep.new_since_baseline, ["com.evil.plist"])
            # baseline updated: second run sees nothing new
            rep2 = launchd.collect_launchd(home=home, state_path=state,
                                           system_dirs=())
            self.assertEqual(rep2.new_since_baseline, [])

    def test_system_dirs_included(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sysd = home / "sys"
            _mk(sysd, "com.sys.plist")
            rep = launchd.collect_launchd(home=home, state_path=home / "b.json",
                                          system_dirs=(sysd,))
            self.assertEqual(rep.agent_count, 1)

    def test_own_agents_excluded(self):
        # wtfssd never alerts on its own LaunchAgents: they are not counted,
        # never reported as new, and never stored in the baseline.
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            agents = home / "Library/LaunchAgents"
            _mk(agents, "com.a.plist")
            _mk(agents, "com.wtfssd.watch.plist")
            _mk(agents, "com.wtfssd.watch.fast.plist")
            state = home / "b.json"
            rep = launchd.collect_launchd(home=home, state_path=state,
                                          system_dirs=())
            self.assertEqual(rep.agent_count, 1)
            self.assertEqual(rep.new_since_baseline, [])
            stored = set(json.loads(state.read_text())["names"])
            self.assertEqual(stored, {"com.a.plist"})
            # own agents added after a baseline exist are still invisible
            rep2 = launchd.collect_launchd(home=home, state_path=state,
                                           system_dirs=())
            self.assertEqual(rep2.agent_count, 1)
            self.assertEqual(rep2.new_since_baseline, [])


if __name__ == "__main__":
    unittest.main()
