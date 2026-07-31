from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wtfssd import optimize


class TestIgnoreMerge(unittest.TestCase):
    def test_creates_new_file(self):
        with tempfile.TemporaryDirectory() as td:
            path, added = optimize.merge_ignore_file(Path(td))
            self.assertEqual(path.name, ".cursorignore")
            self.assertEqual(added, optimize.IGNORE_LINES)
            text = path.read_text()
            self.assertIn(optimize.IGNORE_MARKER, text)
            self.assertIn("node_modules/", text)

    def test_merges_without_clobbering(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            existing = root / ".cursorignore"
            existing.write_text("# my rules\nnode_modules/\nsecret/\n")
            _, added = optimize.merge_ignore_file(root)
            text = existing.read_text()
            self.assertIn("secret/", text)            # user content preserved
            self.assertEqual(text.count("node_modules/"), 1)  # not duplicated
            self.assertEqual(added, [l for l in optimize.IGNORE_LINES
                                     if l != "node_modules/"])
            # second run adds nothing
            _, added2 = optimize.merge_ignore_file(root)
            self.assertEqual(added2, [])


class TestAgent(unittest.TestCase):
    def test_install_writes_plist(self):
        with tempfile.TemporaryDirectory() as td:
            la = Path(td)
            path, loaded = optimize.install_agent(launch_agents_dir=la)
            self.assertTrue(path.exists())
            text = path.read_text()
            self.assertIn("com.wtfssd.watch", text)
            self.assertIn("<key>StartInterval</key>", text)
            self.assertIn("<integer>3600</integer>", text)
            self.assertIn("watch", text)
            self.assertIn("--once", text)
            self.assertFalse(loaded)  # launchctl bootstrap into test dir fails/no-op

    def test_uninstall_removes_plist(self):
        with tempfile.TemporaryDirectory() as td:
            la = Path(td)
            path, _ = optimize.install_agent(launch_agents_dir=la)
            self.assertTrue(optimize.uninstall_agent(launch_agents_dir=la))
            self.assertFalse(path.exists())
            self.assertFalse(optimize.uninstall_agent(launch_agents_dir=la))

    def test_install_fast_agent_writes_plist(self):
        with tempfile.TemporaryDirectory() as td:
            path, loaded = optimize.install_fast_agent(
                launch_agents_dir=Path(td))
            self.assertFalse(loaded)  # tempdir: launchctl untouched
            text = path.read_text()
            self.assertIn("com.wtfssd.watch.fast", text)
            self.assertIn("--fast", text)
            self.assertIn("<integer>300</integer>", text)

    def test_uninstall_removes_fast_label_too(self):
        with tempfile.TemporaryDirectory() as td:
            optimize.install_agent(launch_agents_dir=Path(td))
            optimize.install_fast_agent(launch_agents_dir=Path(td))
            self.assertTrue(optimize.uninstall_agent(launch_agents_dir=Path(td)))
            self.assertTrue(optimize.uninstall_agent(
                label="com.wtfssd.watch.fast", launch_agents_dir=Path(td)))


if __name__ == "__main__":
    unittest.main()
