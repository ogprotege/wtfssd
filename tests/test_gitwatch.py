from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wtfssd.collectors import gitwatch


def _runner_for(status="", remotes="origin\n", log="abc123 work\n"):
    def runner(cmd):
        if "status" in cmd:
            return status
        if cmd[-1] == "remote" or "remote" in cmd and "log" not in cmd:
            return remotes
        if "log" in cmd:
            return log
        return ""
    return runner


class TestGitWatch(unittest.TestCase):
    def test_parse_status(self):
        self.assertEqual(gitwatch.parse_status(
            " M file.py\n?? new.txt\n?? other.txt\nA  added.py\n"), (2, 2))

    def test_collect_repo_full(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".git").mkdir()
            rep = gitwatch.collect_repo(Path(td), runner=_runner_for(
                status=" M a.py\n?? b.txt\n"))
            self.assertIsNone(rep.error)
            self.assertEqual((rep.uncommitted, rep.untracked), (1, 1))
            self.assertTrue(rep.has_remote)
            self.assertEqual(rep.unpushed, 1)

    def test_collect_repo_no_remote_skips_unpushed(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".git").mkdir()
            rep = gitwatch.collect_repo(Path(td), runner=_runner_for(
                remotes="", log=""))
            self.assertFalse(rep.has_remote)
            self.assertEqual(rep.unpushed, 0)

    def test_collect_repo_not_a_repo(self):
        with tempfile.TemporaryDirectory() as td:
            rep = gitwatch.collect_repo(Path(td), runner=_runner_for())
            self.assertEqual(rep.error, "not a git repository")

    def test_collect_gitwatch(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".git").mkdir()
            rep = gitwatch.collect_gitwatch([td], runner=_runner_for())
            self.assertTrue(rep.available)
            self.assertEqual(len(rep.repos), 1)


if __name__ == "__main__":
    unittest.main()
