from __future__ import annotations

import unittest
from pathlib import Path

from wtfssd.collectors import swap

FIXTURE = (Path(__file__).parent / "fixtures" / "sysctl_swap.txt").read_text()
BIG = "vm.swapusage: total = 2048.00M  used = 1536.25M  free = 511.75M  (encrypted)"


def fake_runner(text):
    def run(argv, timeout=15):
        return text
    return run


class TestSwap(unittest.TestCase):
    def test_parse_fixture(self):
        rep = swap.parse_swapusage(FIXTURE)
        self.assertTrue(rep.encrypted)
        self.assertEqual(rep.total_mb, 0.0)
        self.assertEqual(rep.used_mb, 0.0)

    def test_parse_values(self):
        rep = swap.parse_swapusage(BIG)
        self.assertEqual(rep.total_mb, 2048.0)
        self.assertEqual(rep.used_mb, 1536.25)
        self.assertEqual(rep.free_mb, 511.75)

    def test_collect_none_on_failure(self):
        self.assertIsNone(swap.collect_swap(runner=fake_runner(None)))

    def test_collect_ok(self):
        rep = swap.collect_swap(runner=fake_runner(BIG))
        self.assertIsNotNone(rep)
        self.assertEqual(rep.used_mb, 1536.25)

    def test_parse_gigabyte_units(self):
        text = "vm.swapusage: total = 2.00G  used = 1.50G  free = 0.50G  (encrypted)"
        rep = swap.parse_swapusage(text)
        self.assertAlmostEqual(rep.used_mb, 1.50 * 1024)
        self.assertAlmostEqual(rep.total_mb, 2.00 * 1024)

    def test_collect_none_on_unparseable(self):
        self.assertIsNone(swap.collect_swap(runner=fake_runner("vm.swapusage: ???")))


if __name__ == "__main__":
    unittest.main()
