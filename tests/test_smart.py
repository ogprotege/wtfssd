from __future__ import annotations

import unittest
from pathlib import Path

from wtfssd.collectors import smart

FIXTURE = (Path(__file__).parent / "fixtures" / "smartctl.txt").read_text()


def fake_runner(text):
    def run(argv, timeout=15):
        return text
    return run


class TestParseSmartctl(unittest.TestCase):
    def test_parse_fixture(self):
        rep = smart.parse_smartctl(FIXTURE)
        self.assertTrue(rep.available)
        self.assertIsNone(rep.error)
        self.assertIn("APPLE SSD", rep.model)
        self.assertEqual(rep.health, "PASSED")
        self.assertEqual(rep.percent_used, 1)
        self.assertEqual(rep.available_spare, 100)
        self.assertEqual(rep.media_errors, 0)
        self.assertEqual(rep.power_on_hours, 243)
        # Brief pinned 25531425 from an earlier live capture; the fixture
        # captured in this run reports 25,535,302 (SSD keeps writing).
        self.assertEqual(rep.data_units_written, 25535302)
        self.assertAlmostEqual(rep.tb_written, 13.0)

    def test_gb_units_converted_to_tb(self):
        text = "Percentage Used:  3%\nData Units Written:  1,953,125 [1000 GB]\n"
        rep = smart.parse_smartctl(text)
        self.assertEqual(rep.percent_used, 3)
        self.assertAlmostEqual(rep.tb_written, 1.0)

    def test_partial_output_keeps_nones(self):
        rep = smart.parse_smartctl("SMART overall-health self-assessment test result: PASSED\n")
        self.assertTrue(rep.available)
        self.assertEqual(rep.health, "PASSED")
        self.assertIsNone(rep.percent_used)


class TestCollectSmart(unittest.TestCase):
    def test_collect_uses_runner(self):
        rep = smart.collect_smart(runner=fake_runner(FIXTURE))
        self.assertTrue(rep.available)
        self.assertEqual(rep.percent_used, 1)

    def test_missing_smartctl_degrades(self):
        rep = smart.collect_smart(runner=fake_runner(None))
        self.assertFalse(rep.available)
        self.assertIsNotNone(rep.error)

    def test_error_only_stdout_degrades(self):
        rep = smart.collect_smart(runner=fake_runner(
            "smartctl: Unable to detect device type\n"))
        self.assertFalse(rep.available)
        self.assertIsNotNone(rep.error)


if __name__ == "__main__":
    unittest.main()
