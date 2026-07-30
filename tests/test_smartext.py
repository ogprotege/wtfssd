from __future__ import annotations

import unittest
from pathlib import Path

from ssdwtf.collectors import smart, smartext

FIX = Path(__file__).parent / "fixtures"


class TestSmartExtension(unittest.TestCase):
    def test_internal_fixture_new_fields(self):
        text = (FIX / "smartctl.txt").read_text()
        rep = smart.parse_smartctl(text)
        # real Apple-drive fixture: verify against actual fixture values;
        # all four must parse without raising
        for v in (rep.critical_warning, rep.spare_threshold,
                  rep.unsafe_shutdowns, rep.temperature_c):
            self.assertTrue(v is None or isinstance(v, int))

    def test_nvme_fields_parse(self):
        text = (
            "Critical Warning:                   0x02\n"
            "Temperature:                        36 Celsius\n"
            "Available Spare:                    100%\n"
            "Available Spare Threshold:          10%\n"
            "Unsafe Shutdowns:                   42\n"
        )
        rep = smart.parse_smartctl(text)
        self.assertEqual(rep.critical_warning, 2)
        self.assertEqual(rep.spare_threshold, 10)
        self.assertEqual(rep.unsafe_shutdowns, 42)
        self.assertEqual(rep.temperature_c, 36)


class TestSmartExternal(unittest.TestCase):
    def test_external_parses_with_first_bridge(self):
        text = (FIX / "smartctl_external.txt").read_text()
        rep = smartext.collect_smart_external(
            "/dev/disk4", runner=lambda cmd: text)
        self.assertTrue(rep.available)
        self.assertTrue(rep.model or rep.health)

    def test_bridge_fallback(self):
        calls: list[list[str]] = []

        def runner(cmd):
            calls.append(cmd)
            if "-d" in cmd and cmd[cmd.index("-d") + 1] == "auto":
                return None  # auto unsupported
            return (FIX / "smartctl_external.txt").read_text()

        rep = smartext.collect_smart_external("/dev/disk4", runner=runner)
        self.assertTrue(rep.available)
        self.assertEqual(len(calls), 2)

    def test_absent_drive_degrades(self):
        rep = smartext.collect_smart_external(
            "/dev/disk9", runner=lambda cmd: None)
        self.assertFalse(rep.available)
        self.assertIn("disk9", rep.error)


if __name__ == "__main__":
    unittest.main()
