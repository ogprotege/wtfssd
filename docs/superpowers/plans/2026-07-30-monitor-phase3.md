# Monitor Expansion Phase 3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ssdwtf always-on: SwiftBar menu-bar presence, transition-based alerting with per-severity cooldowns, sustained-pressure detection, daily digest command, and a 5-minute fast-tier LaunchAgent.

**Architecture:** Small additive changes to alerts/analyze/cli/optimize, one new artifact (`contrib/swiftbar/ssdwtf.5m.py`). All back-compatible; all 192 existing tests keep passing.

**Tech Stack:** Python ≥3.10 stdlib only; stdlib `unittest`; spec `docs/superpowers/specs/2026-07-30-monitor-expansion.md` §11.

## Global Constraints

- Python standard library ONLY. No third-party imports. No sudo. Never `shell=True`; package code invokes commands only via `collectors._run.run_cmd`. (The SwiftBar plugin is a standalone artifact, not package code; it is also stdlib-only.)
- Project root: `/Users/biscuit/wtfssd`. Branch: `phase-3`. Commit per task.
- models.py is FROZEN this phase — no changes needed; do not touch it.
- Additive-only changes to alerts/analyze/cli/optimize/report. All 192 existing tests pass unmodified.
- The plugin never mutates anything: its menu actions only run read-only scans or open Terminal for the user.
- Run only your own test files from repo root. `from __future__ import annotations`, type hints, LF endings.

---

### Task 1: alerts.py — per-severity cooldowns + transition semantics

**Files:**
- Modify: `ssdwtf/alerts.py`, `ssdwtf/config.py`
- Test: `tests/test_alerts.py` (extend only)

**Interfaces:**
- Produces: `alert()` notifies on (a) new code, (b) severity increase, (c) per-severity cooldown elapsed. State format `{code: {"ts": iso, "severity": sev}}`, tolerant of the old `{code: iso}` format. Config key `alerts.cooldown_critical_hours` (4).

- [ ] **Step 1: Modify `ssdwtf/alerts.py`**

Replace `_load_state` and `alert` with:

```python
def _load_state(state_dir: Path | None) -> dict[str, dict]:
    """Tolerates both formats: new {code: {ts, severity}} and old {code: iso}."""
    try:
        data = json.loads(_state_path(state_dir).read_text())
        if not isinstance(data, dict):
            return {}
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, dict] = {}
    for code, entry in data.items():
        if isinstance(entry, dict) and "ts" in entry:
            out[code] = {"ts": entry["ts"],
                         "severity": entry.get("severity", "warn")}
        elif isinstance(entry, str):
            out[code] = {"ts": entry, "severity": "warn"}  # legacy format
    return out


def alert(findings: list[Finding], config: dict,
          state_dir: Path | None = None,
          notifier: Notifier | None = None,
          now: datetime | None = None) -> list[Finding]:
    """Notify on transitions: new finding code, severity increase, or
    per-severity cooldown elapsed (critical: alerts.cooldown_critical_hours,
    warn: alerts.cooldown_hours). Info findings never notify."""
    if not config.get("alerts", {}).get("enabled", True):
        return []
    now = now or datetime.now()
    cfg = config.get("alerts", {})
    cooldowns = {
        "warn": timedelta(hours=cfg.get("cooldown_hours", 24.0)),
        "critical": timedelta(hours=cfg.get("cooldown_critical_hours", 4.0)),
    }
    rank = {"warn": 1, "critical": 2}
    state = _load_state(state_dir)
    notified: list[Finding] = []
    for f in findings:
        if f.severity not in rank:
            continue
        last = state.get(f.code)
        if last:
            try:
                elapsed = now - datetime.fromisoformat(last["ts"])
            except ValueError:
                elapsed = None
            same_or_lower = rank[last["severity"]] >= rank[f.severity]
            if (same_or_lower and elapsed is not None
                    and elapsed < cooldowns[f.severity]):
                continue  # still inside the cooldown for a non-escalation
        if notify(f, notifier):
            state[f.code] = {"ts": now.isoformat(), "severity": f.severity}
            notified.append(f)
    _save_state(state, state_dir)
    return notified
```

- [ ] **Step 2: Add to `ssdwtf/config.py` DEFAULTS** — change the alerts line to:

```python
    "alerts": {"enabled": True, "cooldown_hours": 24.0,
               "cooldown_critical_hours": 4.0},
```

- [ ] **Step 3: Extend `tests/test_alerts.py`** — append (before `__main__`), following the file's existing fake-notifier/state_dir patterns:

```python
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
```

(Add `import json`, `from pathlib import Path`, `from ssdwtf import models` if the file lacks them.)
- [ ] **Step 4: Run tests** — `python3 -m unittest tests.test_alerts -v` → all pass
- [ ] **Step 5: Commit** — `git add ssdwtf/alerts.py ssdwtf/config.py tests/test_alerts.py && git commit -m "phase3: per-severity cooldowns + escalation transitions in alerts"`

---

### Task 2: analyze.py — sustained pressure + thrash window cap

**Files:**
- Modify: `ssdwtf/analyze.py`
- Test: `tests/test_analyze.py` (extend only)

**Interfaces:**
- Produces: `pressure.warn` requires sustained level ≥ 2 over `pressure.sustained_min` when metrics are available (falls back to point-in-time otherwise); `_swap_rate_gb_day(history, window_days=14.0)`.

- [ ] **Step 1: Modify `ssdwtf/analyze.py`**

Replace the `pressure.warn` elif branch (currently `elif pr.level >= 2:`)
with sustained detection:

```python
        elif pr.level >= 2:
            sustained = True  # fallback: no metrics → point-in-time (Phase-1 behavior)
            if metrics_path is not None:
                samples = metrics.series(
                    "pressure.level",
                    days=config.get("pressure", {}).get("sustained_min", 10) / 1440.0,
                    path=metrics_path)
                if len(samples) >= 2:
                    sustained = (sum(1 for _, v in samples if v >= 2)
                                 / len(samples)) >= 0.5
            if sustained:
                findings.append(_f("monitor", "warn", "pressure.warn",
                    "Memory pressure elevated (sustained)",
                    f"Pressure level {pr.level} with {pr.free_pct:.0f}% free"
                    if pr.free_pct is not None else f"Pressure level {pr.level}",
                    "Watch for swap growth; consider closing unused IDE windows."))
```

Replace the `_swap_rate_gb_day` helper with the windowed version:

```python
def _swap_rate_gb_day(history: list[HealthReport],
                      window_days: float = 14.0) -> float | None:
    """Least-squares slope of swap used (GB/day), trailing window only."""
    cutoff = datetime.now().timestamp() - window_days * 86400.0
    pts: list[tuple[float, float]] = []
    for r in history:
        if r.swap is None:
            continue
        try:
            t = datetime.fromisoformat(r.timestamp).timestamp() / 86400.0
        except ValueError:
            continue
        if t * 86400.0 < cutoff:
            continue
        pts.append((t, r.swap.used_mb / 1024))
    if len(pts) < 2:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    denom = sum((p[0] - mx) ** 2 for p in pts)
    if denom == 0:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / denom
```

- [ ] **Step 2: Extend `tests/test_analyze.py`** — append (before `__main__`):

```python
class TestPhase3Pressure(unittest.TestCase):
    def test_pressure_warn_falls_back_without_metrics(self):
        rep = _base_report()
        rep.pressure = models.PressureReport(available=True, level=2,
                                             free_pct=15.0)
        codes = {f.code for f in analyze.analyze(rep, [], dict(DEFAULTS))}
        self.assertIn("pressure.warn", codes)

    def test_pressure_warn_suppressed_when_not_sustained(self):
        import tempfile
        from pathlib import Path as P
        from ssdwtf import metrics as metrics_mod
        rep = _base_report()
        rep.pressure = models.PressureReport(available=True, level=2)
        with tempfile.TemporaryDirectory() as td:
            db = P(td) / "m.db"
            # 4 samples: only 1 at level >= 2 → not sustained → no warn
            from datetime import datetime, timedelta
            for i, lvl in enumerate([1, 1, 1, 2]):
                ts = (datetime.now() - timedelta(minutes=4 - i)).isoformat(
                    timespec="seconds")
                r = models.make_empty_report(ts, 64.0)
                r.pressure = models.PressureReport(available=True, level=lvl)
                metrics_mod.record(r, path=db)
            codes = {f.code for f in analyze.analyze(
                rep, [], dict(DEFAULTS), metrics_path=db)}
            self.assertNotIn("pressure.warn", codes)

    def test_pressure_warn_fires_when_sustained(self):
        import tempfile
        from pathlib import Path as P
        from ssdwtf import metrics as metrics_mod
        rep = _base_report()
        rep.pressure = models.PressureReport(available=True, level=2)
        with tempfile.TemporaryDirectory() as td:
            db = P(td) / "m.db"
            from datetime import datetime, timedelta
            for i in range(4):
                ts = (datetime.now() - timedelta(minutes=4 - i)).isoformat(
                    timespec="seconds")
                r = models.make_empty_report(ts, 64.0)
                r.pressure = models.PressureReport(available=True, level=2)
                metrics_mod.record(r, path=db)
            codes = {f.code for f in analyze.analyze(
                rep, [], dict(DEFAULTS), metrics_path=db)}
            self.assertIn("pressure.warn", codes)
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_analyze -v` → all pass
- [ ] **Step 4: Commit** — `git add ssdwtf/analyze.py tests/test_analyze.py && git commit -m "phase3: sustained pressure detection + swap slope window cap"`

---

### Task 3: digest command

**Files:**
- Modify: `ssdwtf/report.py`, `ssdwtf/cli.py`
- Test: `tests/test_report.py`, `tests/test_cli.py` (extend only)

**Interfaces:**
- Produces: `report.render_digest(report, findings, stats) -> str` where `stats: dict[str, float | int | None]`; `cli cmd_digest` wiring `ssdwtf digest [--days N] [--json]`.

- [ ] **Step 1: Add to `ssdwtf/report.py`**

```python
def render_digest(report: HealthReport, findings: list[Finding],
                  stats: dict) -> str:
    """One-look daily summary: domains, key deltas, findings by severity."""
    lines = [f"ssdwtf digest — {report.timestamp} "
             f"(window: {stats.get('days', 1)} day(s))", ""]
    lines.append(f"  scans recorded: {stats.get('scans', 0)}")
    domains = stats.get("domains", {})
    if domains:
        worst = max(domains.values(),
                    key=lambda s: {"ok": 0, "unknown": 0, "warn": 1,
                                   "critical": 2}.get(s, 0))
        lines.append(f"  domains: worst = {worst}")
    deltas = [
        ("SSD writes", stats.get("tb_written_delta"), "{:+.2f} TB"),
        ("write rate trend", stats.get("gb_written_per_day"), "{:.1f} GB/day"),
        ("swap (latest)", stats.get("swap_used_gb"), "{:.1f} GB"),
        ("state total (latest)", stats.get("state_total_gb"), "{:.1f} GB"),
        ("logs growth", stats.get("logs_gb_per_day"), "{:+.2f} GB/day"),
        ("backup age", stats.get("backup_age_hours"), "{:.0f} h"),
    ]
    for label, value, fmt in deltas:
        if value is not None:
            lines.append(f"  {label:<20} {fmt.format(value)}")
    sev = {"critical": 0, "warn": 0, "info": 0}
    for f in findings:
        sev[f.severity] = sev.get(f.severity, 0) + 1
    lines.append(f"  findings: {sev['critical']} critical · "
                 f"{sev['warn']} warn · {sev['info']} info")
    score = health_score(findings)
    lines.append(f"  health: {score}/100 ({grade(score)})")
    return "\n".join(lines)
```

- [ ] **Step 2: Add to `ssdwtf/cli.py`**

```python
def cmd_digest(args: argparse.Namespace) -> int:
    config, warn = load_config()
    if warn:
        print(f"warning: {warn}", file=sys.stderr)
    rep, findings, code = _run_scan(config, use_history=True,
                                    fast=getattr(args, "fast", False))
    days = args.days
    stats = {
        "days": days,
        "scans": len(history.load_history(limit=None)),
        "domains": analyze.domain_statuses(findings, rep),
        "tb_written_delta": None,
        "gb_written_per_day": history.gb_written_per_day(
            history.load_history()),
        "swap_used_gb": rep.swap.used_mb / 1024 if rep.swap else None,
        "state_total_gb": (rep.statedirs.total_bytes / 1e9
                           if rep.statedirs.dirs else None),
        "logs_gb_per_day": metrics.rate_per_day("logs.total_gb", days=days),
        "backup_age_hours": (rep.backup.last_backup_age_hours
                             if rep.backup.available else None),
    }
    series = metrics.series("smart.tb_written", days=days)
    if len(series) >= 2:
        stats["tb_written_delta"] = series[-1][1] - series[0][1]
    if args.json:
        print(json.dumps({"stats": stats, "findings": [
            {"severity": f.severity, "code": f.code, "title": f.title}
            for f in findings]}, indent=2, default=str))
    else:
        print(report_mod.render_digest(rep, findings, stats))
    return code
```

Register in `build_parser` (after the `history` parser block):

```python
    p = sub.add_parser("digest", help="one-look daily summary")
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_digest)
```

- [ ] **Step 3: Extend tests**

`tests/test_report.py` — append:

```python
class TestDigest(unittest.TestCase):
    def test_render_digest_shape(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        out = report.render_digest(rep, [], {
            "days": 1, "scans": 5, "domains": {"drive": "ok"},
            "swap_used_gb": 1.5, "state_total_gb": 43.2,
            "backup_age_hours": 70.0})
        self.assertIn("digest", out)
        self.assertIn("1.5 GB", out)
        self.assertIn("43.2 GB", out)
        self.assertIn("health: 100/100", out)
```

(`models` import if absent.)

`tests/test_cli.py` — append a digest smoke test following the file's
mocking pattern: patch `cli._run_scan` to return a known
(report, findings, 0), patch `cli.metrics.series`/`rate_per_day` and
`cli.history.load_history`/`gb_written_per_day`, run
`cli.main(["digest", "--json"])` with stdout redirected, assert exit 0 and
the JSON parses with a `stats` key.

- [ ] **Step 4: Run tests** — `python3 -m unittest tests.test_report tests.test_cli -v` → all pass
- [ ] **Step 5: Commit** — `git add ssdwtf/report.py ssdwtf/cli.py tests/test_report.py tests/test_cli.py && git commit -m "phase3: digest command"`

---

### Task 4: Fast-tier LaunchAgent (optimize.py)

**Files:**
- Modify: `ssdwtf/optimize.py`, `ssdwtf/cli.py`, `ssdwtf/config.py`
- Test: `tests/test_optimize.py` (extend only)

**Interfaces:**
- Produces: `install_fast_agent(interval_seconds=300, label="com.ssdwtf.watch.fast", launch_agents_dir=None) -> tuple[Path, bool]`; `optimize install-agent` installs both agents; `uninstall-agent` removes both. Config key `watch.fast_interval_minutes` (5).

- [ ] **Step 1: Modify `ssdwtf/optimize.py`**

Change `_program_args` to accept a fast flag:

```python
def _program_args(fast: bool = False) -> list[str]:
    """How to invoke ssdwtf: installed script if present, else python -m from source."""
    from shutil import which
    tail = ["watch", "--once"] + (["--fast"] if fast else [])
    exe = which("ssdwtf")
    if exe:
        return [exe] + tail
    return [sys.executable, "-m", "ssdwtf"] + tail
```

Change `_plist` to thread it through:

```python
def _plist(label: str, interval_seconds: int, log_path: Path,
           fast: bool = False) -> str:
    args = _program_args(fast=fast)
```

(the rest of `_plist` is unchanged).

Append:

```python
def install_fast_agent(interval_seconds: int = 300,
                       label: str = "com.ssdwtf.watch.fast",
                       launch_agents_dir: Path | None = None) -> tuple[Path, bool]:
    """5-minute fast-tier watcher (watch --once --fast) alongside the hourly
    full agent. Same launchctl probe semantics as install_agent."""
    from .config import data_dir
    agents = launch_agents_dir or (Path.home() / "Library" / "LaunchAgents")
    agents.mkdir(parents=True, exist_ok=True)
    plist_path = agents / f"{label}.plist"
    log_path = data_dir() / "watch-fast.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(_plist(label, interval_seconds, log_path,
                                 fast=True))
    loaded = False
    if launch_agents_dir is None:
        run_cmd(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"])
        run_cmd(["launchctl", "bootstrap", f"gui/{os.getuid()}",
                 str(plist_path)])
        loaded = run_cmd(["launchctl", "print",
                          f"gui/{os.getuid()}/{label}"]) is not None
    return plist_path, loaded
```

- [ ] **Step 2: Modify `ssdwtf/cli.py` install/uninstall paths**

In `cmd_optimize`, replace the `install-agent` block with:

```python
    if args.opt_command == "install-agent":
        path, loaded = optimize.install_agent()
        print(f"wrote {path}")
        print("loaded with launchctl" if loaded else
              f"not loaded — run: launchctl bootstrap gui/$(id -u) {path}")
        config, _ = load_config()
        interval = int(config.get("watch", {}).get("fast_interval_minutes", 5)) * 60
        fpath, floaded = optimize.install_fast_agent(interval_seconds=interval)
        print(f"wrote {fpath} (fast tier, every {interval // 60} min)")
        print("loaded with launchctl" if floaded else
              f"not loaded — run: launchctl bootstrap gui/$(id -u) {fpath}")
        return 0
```

and the `uninstall-agent` block with:

```python
    if args.opt_command == "uninstall-agent":
        removed = optimize.uninstall_agent()
        fast_removed = optimize.uninstall_agent(label="com.ssdwtf.watch.fast")
        n = int(removed) + int(fast_removed)
        print(f"{n} agent(s) removed" if n else "no agent installed")
        return 0
```

- [ ] **Step 3: Add to `ssdwtf/config.py` DEFAULTS** — change the watch line to:

```python
    "watch": {"interval_minutes": 60, "fast_interval_minutes": 5},
```

- [ ] **Step 4: Extend `tests/test_optimize.py`** — append (before `__main__`), following the file's existing tempdir pattern:

```python
    def test_install_fast_agent_writes_plist(self):
        with tempfile.TemporaryDirectory() as td:
            path, loaded = optimize.install_fast_agent(
                launch_agents_dir=Path(td))
            self.assertFalse(loaded)  # tempdir: launchctl untouched
            text = path.read_text()
            self.assertIn("com.ssdwtf.watch.fast", text)
            self.assertIn("--fast", text)
            self.assertIn("<integer>300</integer>", text)

    def test_uninstall_removes_fast_label_too(self):
        with tempfile.TemporaryDirectory() as td:
            optimize.install_agent(launch_agents_dir=Path(td))
            optimize.install_fast_agent(launch_agents_dir=Path(td))
            self.assertTrue(optimize.uninstall_agent(launch_agents_dir=Path(td)))
            self.assertTrue(optimize.uninstall_agent(
                label="com.ssdwtf.watch.fast", launch_agents_dir=Path(td)))
```

(Add `from pathlib import Path` / `import tempfile` if absent.)
- [ ] **Step 5: Run tests** — `python3 -m unittest tests.test_optimize -v` → all pass
- [ ] **Step 6: Commit** — `git add ssdwtf/optimize.py ssdwtf/cli.py ssdwtf/config.py tests/test_optimize.py && git commit -m "phase3: fast-tier LaunchAgent (5-min watch --once --fast)"`

---

### Task 5: SwiftBar menu-bar plugin

**Files:**
- Create: `contrib/swiftbar/ssdwtf.5m.py` (executable, stdlib Python 3)
- Test: `tests/test_swiftbar.py`

**Interfaces:**
- Produces: the plugin artifact. Not imported by the package; tested via subprocess with the `SSDWTF_JSON` env hook.

- [ ] **Step 1: Write `contrib/swiftbar/ssdwtf.5m.py`**

```python
#!/usr/bin/env python3
"""ssdwtf menu-bar plugin for SwiftBar/xbar.

Menu bar: SSD:<grade> colored by worst severity.
Dropdown: score, ten domains, top findings, actions.
Refresh: every 5 minutes (the .5m. in the filename). No mutation: actions
only run read-only scans or open Terminal for the user.

Test hook: SSDWTF_JSON env var supplies a canned scan payload.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__))))

_COLORS = {"critical": "red", "warn": "yellow", "ok": "green",
           "unknown": "gray", "info": "blue"}
_MARKS = {"ok": "✅", "warn": "⚠️", "critical": "🔴", "unknown": "❔"}


def _payload() -> dict:
    override = os.environ.get("SSDWTF_JSON")
    if override:
        return json.loads(override)
    exe = shutil.which("ssdwtf")
    cmd = ([exe] if exe else
           [sys.executable, "-m", "ssdwtf"]) + [
        "scan", "--fast", "--json", "--no-history"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                         cwd=None if exe else _REPO_ROOT)
    return json.loads(out.stdout)


def main() -> None:
    try:
        data = _payload()
    except Exception:
        print("SSD:? | color=gray")
        print("---")
        print("ssdwtf scan failed — is the package installed?")
        raise SystemExit(0)

    findings = data.get("findings", [])
    rank = {"critical": 2, "warn": 1, "info": 0}
    worst = "ok"
    for f in findings:
        if rank.get(f.get("severity"), 0) > rank.get(worst, 0):
            worst = f["severity"]
    grade = data.get("grade", "?")
    print(f"SSD:{grade} | color={_COLORS.get(worst, 'green')}")
    print("---")
    print(f"Health {data.get('score', '?')}/100 ({grade})")
    domains = data.get("domains", {})
    if domains:
        print("---")
        for name, status in domains.items():
            print(f"{_MARKS.get(status, '❔')} {name} | color={_COLORS.get(status, 'gray')}")
    if findings:
        print("---")
        order = {"critical": 0, "warn": 1, "info": 2}
        for f in sorted(findings,
                        key=lambda f: order.get(f.get("severity"), 3))[:5]:
            print(f"[{f.get('severity', '?').upper()}] {f.get('title', '')[:70]}")
    print("---")
    print("Run full scan | bash=ssdwtf param1=scan terminal=true")
    print("Refresh | refresh=true")


if __name__ == "__main__":
    main()
```

Make it executable: `chmod +x contrib/swiftbar/ssdwtf.5m.py`

- [ ] **Step 2: Write `tests/test_swiftbar.py`**

```python
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN = (Path(__file__).parent.parent / "contrib" / "swiftbar"
          / "ssdwtf.5m.py")

PAYLOAD = {
    "score": 68, "grade": "C",
    "domains": {"drive": "ok", "backup": "critical", "memory": "ok",
                "work": "unknown"},
    "findings": [
        {"severity": "critical", "code": "backup.stale",
         "title": "Last successful backup 9 days ago"},
        {"severity": "info", "code": "smart.wear_info", "title": "wear 2%"},
    ],
}


class TestSwiftBar(unittest.TestCase):
    def _run(self, payload=PAYLOAD):
        env = dict(os.environ, SSDWTF_JSON=json.dumps(payload))
        return subprocess.run([sys.executable, str(PLUGIN)],
                              capture_output=True, text=True, env=env,
                              timeout=30)

    def test_renders_title_colored_by_worst(self):
        out = self._run().stdout
        self.assertTrue(out.startswith("SSD:C | color=red"))
        self.assertIn("Health 68/100 (C)", out)
        self.assertIn("🔴 backup", out)
        self.assertIn("[CRITICAL] Last successful backup 9 days ago", out)
        self.assertIn("Refresh | refresh=true", out)

    def test_clean_payload_is_green(self):
        out = self._run({"score": 100, "grade": "A", "domains": {},
                         "findings": []}).stdout
        self.assertTrue(out.startswith("SSD:A | color=green"))

    def test_bad_payload_degrades_to_gray(self):
        env = dict(os.environ, SSDWTF_JSON="{not json")
        out = subprocess.run([sys.executable, str(PLUGIN)],
                             capture_output=True, text=True, env=env,
                             timeout=30)
        self.assertEqual(out.returncode, 0)
        self.assertTrue(out.stdout.startswith("SSD:? | color=gray"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_swiftbar -v` → 3 OK
- [ ] **Step 4: Commit** — `git add contrib/swiftbar/ssdwtf.5m.py tests/test_swiftbar.py && git commit -m "phase3: SwiftBar menu-bar plugin"`

---

### Task 6: Docs sync + full verification

**Files:**
- Modify: `README.md`, `AGENTS.md`

- [ ] **Step 1: README.md** — add: menu-bar section (SwiftBar install: `brew install --cask swiftbar`, then `ln -s "$(pwd)/contrib/swiftbar/ssdwtf.5m.py" "$HOME/Library/Application Support/SwiftBar/Plugins/"`); `digest` command; fast-tier agent behavior of `optimize install-agent` (two agents: hourly full + 5-min fast); alert semantics (per-severity cooldowns, escalation); sustained-pressure note. Match existing structure.
- [ ] **Step 2: AGENTS.md** — code-organization: `contrib/swiftbar/ssdwtf.5m.py`, digest in cli summary; config keys `alerts.cooldown_critical_hours`, `watch.fast_interval_minutes`; runtime state adds `watch-fast.log`; test count from your verification run; alert semantics paragraph updated (transitions + per-severity cooldowns).
- [ ] **Step 3: Full verification (from repo root)**

```sh
python3 -m unittest discover -s tests 2>&1 | tail -3   # record count
python3 -m ssdwtf digest; echo "digest exit: $?"
python3 -m ssdwtf digest --json | python3 -m json.tool >/dev/null && echo "digest json ok"
python3 -m ssdwtf scan --fast; echo "fast exit: $?"
python3 contrib/swiftbar/ssdwtf.5m.py | head -5        # live plugin render
python3 -m ssdwtf optimize install-agent               # real install: both agents
launchctl print gui/$(id -u)/com.ssdwtf.watch.fast | head -3
python3 -m ssdwtf optimize uninstall-agent             # and clean removal again
```

All must succeed without tracebacks; record outputs. The real install/uninstall
verifies the launchctl probe path end-to-end.
- [ ] **Step 4: Commit** — `git add README.md AGENTS.md && git commit -m "phase3: docs sync (README, AGENTS)"`

---

## Self-Review Notes (already applied)

- Alert escalation compares severity ranks; a warn→critical escalation inside
  the warn cooldown notifies immediately, while critical→warn (de-escalation)
  does not re-notify inside the warn cooldown.
- The plugin title deliberately shows only the grade (not the score) to keep
  the menu bar compact; the dropdown carries the score.
- `cmd_digest` runs a live scan (recording history+metrics) so the digest is
  never stale-by-one-pass.
