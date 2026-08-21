from __future__ import annotations

import unittest

from wtfssd.collectors import spotlight

PS = """%CPU COMM
0.0 launchd
137.5 /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/Metadata.framework/Versions/A/Support/mds_stores
12.5 /System/.../mdworker
2.0 Cursor
"""


class TestSpotlight(unittest.TestCase):
    def test_parse_mdutil(self):
        self.assertTrue(spotlight.parse_mdutil("/:\n\tIndexing enabled. "))
        self.assertFalse(spotlight.parse_mdutil("/:\n\tIndexing disabled."))
        self.assertFalse(spotlight.parse_mdutil(
            "/:\n\tIndexing and searching disabled."))
        self.assertIsNone(spotlight.parse_mdutil("garbage"))

    def test_parse_mds_cpu(self):
        self.assertEqual(spotlight.parse_mds_cpu(PS), 150.0)

    def test_collect(self):
        def runner(cmd):
            return "/:\n\tIndexing enabled. " if "mdutil" in cmd else PS
        rep = spotlight.collect_spotlight(runner=runner)
        self.assertTrue(rep.available)
        self.assertTrue(rep.indexing_enabled)
        self.assertEqual(rep.mds_cpu_pct, 150.0)

    def test_collect_degrades(self):
        rep = spotlight.collect_spotlight(runner=lambda cmd: None)
        self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
