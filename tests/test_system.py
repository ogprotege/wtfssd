from __future__ import annotations

import unittest
from pathlib import Path

from ssdwtf.collectors import system

FIX = Path(__file__).parent / "fixtures"
# boottime fixture: Mon Jul 27 18:30:50 2026 → epoch 1785191450
NOW = 1785191450 + 3.5 * 86400  # 3.5 days after boot


def _runner(cmd):
    if cmd[:2] == ["sysctl", "kern.boottime"]:
        return (FIX / "sysctl_boottime.txt").read_text()
    if cmd[:2] == ["pmset", "-g"]:
        return (FIX / "pmset_therm.txt").read_text()
    if "ioreg" in cmd:
        return (FIX / "ioreg_battery.txt").read_text()
    return None


class TestSystem(unittest.TestCase):
    def test_parse_boot_time(self):
        text = (FIX / "sysctl_boottime.txt").read_text()
        self.assertEqual(system.parse_boot_time(text), 1785191450)
        self.assertIsNone(system.parse_boot_time("garbage"))

    def test_parse_speed_limit_default_100(self):
        text = (FIX / "pmset_therm.txt").read_text()  # "No ... recorded" notes
        self.assertEqual(system.parse_cpu_speed_limit(text), 100)

    def test_parse_speed_limit_throttled(self):
        self.assertEqual(system.parse_cpu_speed_limit(
            "CPU_Speed_Limit \t= 62"), 62)

    def test_parse_battery(self):
        text = (FIX / "ioreg_battery.txt").read_text()
        cycle, cap = system.parse_battery(text)
        self.assertEqual(cycle, 9)
        self.assertEqual(cap, 100)

    def test_collect_real_fixtures(self):
        rep = system.collect_system(runner=_runner, now=NOW)
        self.assertTrue(rep.available)
        self.assertAlmostEqual(rep.uptime_days, 3.5, places=1)
        self.assertEqual(rep.cpu_speed_limit, 100)
        self.assertTrue(rep.battery_present)
        self.assertEqual(rep.battery_cycle_count, 9)

    def test_collect_degrades(self):
        rep = system.collect_system(runner=lambda cmd: None)
        self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
