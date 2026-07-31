from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from wtfssd import alerts, models


def finding(sev: str, code: str) -> models.Finding:
    return models.Finding(pillar="monitor", severity=sev, code=code,
                          title="T", detail="D", recommendation="R")

CONFIG = {"alerts": {"enabled": True, "cooldown_hours": 24.0}}
NOW = datetime(2026, 7, 30, 12, 0, 0)


class TestAlerts(unittest.TestCase):
    def test_notifies_warn_and_critical_not_info(self):
        sent = []
        with tempfile.TemporaryDirectory() as td:
            notified = alerts.alert(
                [finding("info", "a"), finding("warn", "b"), finding("critical", "c")],
                CONFIG, state_dir=Path(td), notifier=lambda f: sent.append(f.code) or True,
                now=NOW)
        self.assertEqual(sent, ["b", "c"])
        self.assertEqual([f.code for f in notified], ["b", "c"])

    def test_cooldown_suppresses_repeat(self):
        sent = []
        with tempfile.TemporaryDirectory() as td:
            alerts.alert([finding("warn", "b")], CONFIG, state_dir=Path(td),
                         notifier=lambda f: sent.append(f.code) or True, now=NOW)
            # 1 hour later: still in cooldown
            alerts.alert([finding("warn", "b")], CONFIG, state_dir=Path(td),
                         notifier=lambda f: sent.append(f.code) or True,
                         now=NOW + timedelta(hours=1))
            # 25 hours later: fires again
            alerts.alert([finding("warn", "b")], CONFIG, state_dir=Path(td),
                         notifier=lambda f: sent.append(f.code) or True,
                         now=NOW + timedelta(hours=25))
        self.assertEqual(sent, ["b", "b"])

    def test_disabled_config_notifies_nothing(self):
        sent = []
        cfg = {"alerts": {"enabled": False, "cooldown_hours": 24.0}}
        with tempfile.TemporaryDirectory() as td:
            notified = alerts.alert([finding("critical", "c")], cfg, state_dir=Path(td),
                                    notifier=lambda f: sent.append(f.code) or True, now=NOW)
        self.assertEqual(sent, [])
        self.assertEqual(notified, [])

    def test_failed_notification_not_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            notified = alerts.alert([finding("warn", "b")], CONFIG, state_dir=Path(td),
                                    notifier=lambda f: False, now=NOW)
        self.assertEqual(notified, [])
        state = alerts._load_state(Path(td))
        self.assertNotIn("b", state)

    def test_notify_builds_osascript(self):
        calls = []
        def fake_runner(argv, timeout=15):
            calls.append(argv)
            return "ok\n"
        f = finding("warn", "x")
        f.title = 'High "swap"'
        ok = alerts.notify(f, notifier=lambda fa: alerts._osascript_notify(fa, fake_runner))
        self.assertTrue(ok)
        argv = calls[0]
        self.assertTrue(argv[0].endswith("osascript"))
        self.assertEqual(argv[-2:], ["-e", 'return "ok"'])
        self.assertEqual(argv.count("-e"), 2)
        script = argv[2]
        self.assertIn("display notification", script)
        self.assertNotIn('"swap"', script.split("display notification")[1].split("with title")[0]
                         .replace('\\"', ""))  # quotes escaped

    def test_osascript_notify_failure_returns_false(self):
        def failing_runner(argv, timeout=15):
            return None
        f = finding("warn", "x")
        self.assertFalse(alerts._osascript_notify(f, failing_runner))


    def test_escalation_notifies_inside_cooldown(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = {"alerts": {"enabled": True, "cooldown_hours": 24.0,
                              "cooldown_critical_hours": 4.0}}
            sent = []
            now = datetime.now()
            warn = models.Finding(pillar="monitor", severity="warn",
                                  code="x.y", title="t", detail="d",
                                  recommendation="r")
            crit = models.Finding(pillar="monitor", severity="critical",
                                  code="x.y", title="t", detail="d",
                                  recommendation="r")
            alerts.alert([warn], cfg, state_dir=Path(td),
                         notifier=lambda f: sent.append(f) or True, now=now)
            # escalation warn→critical 1h later: notifies despite cooldown
            got = alerts.alert([crit], cfg, state_dir=Path(td),
                               notifier=lambda f: sent.append(f) or True,
                               now=now + timedelta(hours=1))
            self.assertEqual(len(got), 1)
            self.assertEqual(len(sent), 2)

    def test_critical_cooldown_shorter_than_warn(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = {"alerts": {"enabled": True, "cooldown_hours": 24.0,
                              "cooldown_critical_hours": 4.0}}
            now = datetime.now()
            crit = models.Finding(pillar="monitor", severity="critical",
                                  code="x.y", title="t", detail="d",
                                  recommendation="r")
            ok = lambda f: True
            alerts.alert([crit], cfg, state_dir=Path(td), notifier=ok, now=now)
            # 5h later: critical cooldown (4h) elapsed → notifies again
            got = alerts.alert([crit], cfg, state_dir=Path(td), notifier=ok,
                               now=now + timedelta(hours=5))
            self.assertEqual(len(got), 1)
            # 1h after that: still inside → silent
            got = alerts.alert([crit], cfg, state_dir=Path(td), notifier=ok,
                               now=now + timedelta(hours=6))
            self.assertEqual(got, [])

    def test_legacy_state_format_tolerated(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "alert_state.json").write_text(
                json.dumps({"x.y": datetime.now().isoformat()}))
            cfg = {"alerts": {"enabled": True, "cooldown_hours": 24.0}}
            warn = models.Finding(pillar="monitor", severity="warn",
                                  code="x.y", title="t", detail="d",
                                  recommendation="r")
            got = alerts.alert([warn], cfg, state_dir=Path(td),
                               notifier=lambda f: True)
            self.assertEqual(got, [])  # legacy ts honored as cooldown

    def test_corrupt_state_entry_tolerated(self):
        # non-string ts (TypeError) + unknown severity (not in rank):
        # must not raise, and the finding notifies normally
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "alert_state.json").write_text(
                json.dumps({"a.b": {"ts": 123, "severity": "weird"}}))
            sent = []
            got = alerts.alert([finding("warn", "a.b")], CONFIG,
                               state_dir=Path(td),
                               notifier=lambda f: sent.append(f.code) or True,
                               now=NOW)
            self.assertEqual(sent, ["a.b"])
            self.assertEqual([f.code for f in got], ["a.b"])


if __name__ == "__main__":
    unittest.main()
