from __future__ import annotations

import unittest

from wtfssd.collectors import fds

LSOF = """COMMAND     PID  USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
Cursor     1001 biscuit cwd  DIR  1,4      640  123 /
Cursor     1001 biscuit txt  REG  1,4   123456  124 /a
Cursor     1001 biscuit  42u IPv4                  TCP *:80
Code       1002 biscuit cwd  DIR  1,4      640  125 /
sshd       1003 root    cwd  DIR  1,4      640  126 /
"""


class TestFds(unittest.TestCase):
    def test_parse_lsof(self):
        counts = fds.parse_lsof(LSOF)
        self.assertEqual(counts[1001], ("Cursor", 3))
        self.assertEqual(counts[1003], ("sshd", 1))

    def test_collect_aggregates_family_and_max(self):
        rep = fds.collect_fds(runner=lambda cmd: LSOF)
        self.assertTrue(rep.available)
        self.assertEqual(rep.per_app.get("cursor"), 3)
        self.assertEqual(rep.max_pid, 1001)
        self.assertEqual(rep.max_count, 3)
        self.assertNotIn("sshd", rep.per_app)

    def test_collect_degrades(self):
        rep = fds.collect_fds(runner=lambda cmd: None)
        self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
