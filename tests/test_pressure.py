from __future__ import annotations

import unittest
from pathlib import Path

from ssdwtf.collectors import pressure

FIX = Path(__file__).parent / "fixtures"


def _runner_fixture(cmd):
    if "sysctl" in cmd:
        return (FIX / "sysctl_pressure.txt").read_text()
    if "memory_pressure" in cmd:
        return (FIX / "memory_pressure.txt").read_text()
    return None


class TestPressure(unittest.TestCase):
    def test_parse_level(self):
        self.assertEqual(pressure.parse_pressure_level("1\n"), 1)
        self.assertEqual(pressure.parse_pressure_level("4"), 4)
        self.assertIsNone(pressure.parse_pressure_level("garbage"))

    def test_parse_free_pct(self):
        text = (FIX / "memory_pressure.txt").read_text()
        self.assertEqual(pressure.parse_memory_pressure_free(text), 70.0)
        self.assertIsNone(pressure.parse_memory_pressure_free("no match"))

    def test_collect_real_fixture(self):
        rep = pressure.collect_pressure(runner=_runner_fixture)
        self.assertTrue(rep.available)
        self.assertEqual(rep.level, 1)
        self.assertEqual(rep.free_pct, 70.0)

    def test_collect_degrades(self):
        rep = pressure.collect_pressure(runner=lambda cmd: None)
        self.assertFalse(rep.available)
        self.assertIsNotNone(rep.error)

    def test_collect_unparseable(self):
        rep = pressure.collect_pressure(runner=lambda cmd: "???")
        self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
