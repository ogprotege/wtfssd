from __future__ import annotations

import unittest

from ssdwtf.collectors._run import run_cmd


class TestRunCmd(unittest.TestCase):
    def test_success_returns_stdout(self) -> None:
        self.assertEqual(run_cmd(["/bin/echo", "hello"]), "hello\n")

    def test_missing_binary_returns_none(self) -> None:
        self.assertIsNone(run_cmd(["/nonexistent/binary-xyz"]))

    def test_nonzero_exit_empty_stdout_returns_none(self) -> None:
        self.assertIsNone(run_cmd(["/usr/bin/false"]))

    def test_nonzero_exit_with_stdout_returns_stdout(self) -> None:
        self.assertEqual(run_cmd(["/bin/sh", "-c", "echo data; exit 4"]), "data\n")


if __name__ == "__main__":
    unittest.main()
