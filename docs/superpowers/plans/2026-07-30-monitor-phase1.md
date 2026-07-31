# Monitor Expansion Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend ssdwtf v0.1.0 into a tiered continuous monitor: sqlite baseline store, seven new collectors (pressure, system, apfs, backup, crashes, writerate, external SMART), extended SMART parsing, domain dashboard, `--fast` scan tier.

**Architecture:** Stdlib-only additions to the existing package. New collectors follow the established pattern (pure `parse_*` + runner-injected `collect_*`, never raise). New dataclasses are additive with defaults so all 81 existing tests keep passing. A stdlib `sqlite3` metrics store records canonical metrics on every scan.

**Tech Stack:** Python ≥3.10 stdlib only; stdlib `unittest`; spec `docs/superpowers/specs/2026-07-30-monitor-expansion.md`; base spec `docs/superpowers/specs/2026-07-30-ssdwtf-design.md`.

## Global Constraints

- Python standard library ONLY. No third-party imports. No pip installs.
- Project root: `/Users/biscuit/wtfssd`. Package: `ssdwtf/`. Tests: `tests/`.
- **No sudo.** Every collector works as a normal user or degrades to `available=False`.
- External commands invoked only via `collectors._run.run_cmd` (never `shell=True`, never direct `subprocess` elsewhere).
- Collectors never raise. Failures → `available=False`/`error` or empty structures + `note`.
- Every command-driven collector accepts `runner` (defaults to `_run.run_cmd`). Pure-filesystem collectors accept a `home`/`dir` path parameter instead (statedirs pattern).
- `from __future__ import annotations` at top of every module. Type hints on public functions. LF endings.
- models.py changes are ADDITIVE ONLY: new dataclasses, new fields with defaults. No renames, no removals. All 81 existing tests must pass unmodified, except `tests/test_report.py` may be extended (never weakened) in Task 11 for the domains payload.
- Never store a zero for unavailable data: metrics are recorded only when the source collector has a real value (`None` → skip the metric).
- Run only your own test files: `python3 -m unittest tests.test_<name> -v` from repo root.
- Fixtures already captured from this machine (do NOT recapture): `tests/fixtures/{sysctl_pressure,memory_pressure,sysctl_boottime,pmset_therm,ioreg_battery,tmutil_snapshots,tmutil_destinations,tmutil_latestbackup,diskutil_info,iostat,smartctl_external}.txt`.
- Git: work happens on branch `phase-1`. Commit per task.

---

### Task 1: Metrics store (metrics.py)

**Files:**
- Create: `ssdwtf/metrics.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- Consumes: `ssdwtf.config.data_dir`, `ssdwtf.models.HealthReport` (current shape; new fields arrive in Task 2 — `record` reads them with `getattr(report, "pressure", None)` style guards so Task 1 lands before Task 2).
- Produces: `record(report) -> None`, `series(metric, days, path=None) -> list[tuple[str, float]]`, `rate_per_day(metric, days, path=None) -> float | None`, `latest(metric, path=None) -> float | None`, `db_path() -> Path`. Task 11 calls `record`; later phases call `series`/`rate_per_day`.

- [ ] **Step 1: Write `ssdwtf/metrics.py`**

```python
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import data_dir as default_data_dir
from .models import HealthReport

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
  ts TEXT NOT NULL,
  metric TEXT NOT NULL,
  value REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_metric_ts ON samples(metric, ts);
"""

# Canonical metric set (spec §3.3). Values are extracted with guards so a
# collector that was skipped or failed simply contributes nothing.
_GB = 1e9


def db_path() -> Path:
    return default_data_dir() / "metrics.db"


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    return conn


def _extract(report: HealthReport) -> dict[str, float]:
    """Flatten a HealthReport into canonical metrics. Unavailable/None → absent."""
    out: dict[str, float] = {}

    def put(name: str, value) -> None:
        if value is not None:
            out[name] = float(value)

    s = report.smart
    if s.available:
        put("smart.percent_used", s.percent_used)
        put("smart.tb_written", s.tb_written)
        put("smart.media_errors", s.media_errors)
        put("smart.available_spare", s.available_spare)
    if report.swap is not None:
        put("swap.used_gb", report.swap.used_mb / 1024)
    if report.disk is not None:
        put("disk.pct_free", report.disk.pct_free)
        put("disk.avail_gb", report.disk.avail_gb)
    p = report.processes
    if not p.note:
        put("procs.ghost_count", len(p.ghosts))
        put("procs.total_ide", p.total_ide_processes)
    sd = report.statedirs
    if sd.dirs:
        put("state.total_gb", sd.total_bytes / _GB)
        for d in sd.dirs:
            if d.key == "cursor-vscdb" and d.exists:
                put("state.vscdb_gb", d.size_bytes / _GB)

    # Phase-1 fields (absent until models.py extension; getattr guards keep
    # this module working against the pre-extension HealthReport too).
    pressure = getattr(report, "pressure", None)
    if pressure is not None and getattr(pressure, "available", False):
        put("pressure.level", pressure.level)
    system = getattr(report, "system", None)
    if system is not None and getattr(system, "available", False):
        put("system.uptime_days", system.uptime_days)
        put("system.cpu_speed_limit", system.cpu_speed_limit)
        put("battery.cycle_count", system.battery_cycle_count)
        put("battery.max_capacity_pct", system.battery_max_capacity_pct)
    wr = getattr(report, "writerate", None)
    if wr is not None and getattr(wr, "available", False):
        put("writerate.mb_s", wr.mb_per_s)
    apfs = getattr(report, "apfs", None)
    if apfs is not None and getattr(apfs, "available", False):
        put("apfs.local_snapshot_count", apfs.snapshot_count)
        put("apfs.container_free_gb", apfs.container_free_gb)
    backup = getattr(report, "backup", None)
    if backup is not None and getattr(backup, "available", False):
        put("backup.destination_present", 1.0 if backup.destination_present else 0.0)
        put("backup.last_backup_age_hours", backup.last_backup_age_hours)
    crashes = getattr(report, "crashes", None)
    if crashes is not None and getattr(crashes, "available", False):
        put("crashes.weekly_count", crashes.total_weekly)
    return out


def record(report: HealthReport, path: Optional[Path] = None) -> None:
    """Insert one sample per available metric. Never raises."""
    try:
        rows = _extract(report)
        if not rows:
            return
        conn = _connect(path or db_path())
        try:
            conn.executemany(
                "INSERT INTO samples (ts, metric, value) VALUES (?, ?, ?)",
                [(report.timestamp, name, value) for name, value in rows.items()],
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        return  # monitoring must never break the scan


def _day_cutoff(days: float) -> str:
    from datetime import timedelta
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


def series(metric: str, days: float,
           path: Optional[Path] = None) -> list[tuple[str, float]]:
    try:
        conn = _connect(path or db_path())
        try:
            cur = conn.execute(
                "SELECT ts, value FROM samples WHERE metric = ? AND ts >= ? "
                "ORDER BY ts", (metric, _day_cutoff(days)))
            return [(ts, float(v)) for ts, v in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        return []


def rate_per_day(metric: str, days: float,
                 path: Optional[Path] = None) -> Optional[float]:
    """Least-squares slope in units/day over the window. None if < 2 points."""
    pts = series(metric, days, path)
    if len(pts) < 2:
        return None
    try:
        xs = [datetime.fromisoformat(ts).timestamp() / 86400.0 for ts, _ in pts]
    except ValueError:
        return None
    ys = [v for _, v in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def latest(metric: str, path: Optional[Path] = None) -> Optional[float]:
    try:
        conn = _connect(path or db_path())
        try:
            cur = conn.execute(
                "SELECT value FROM samples WHERE metric = ? "
                "ORDER BY ts DESC LIMIT 1", (metric,))
            row = cur.fetchone()
            return float(row[0]) if row else None
        finally:
            conn.close()
    except Exception:
        return None
```

- [ ] **Step 2: Write `tests/test_metrics.py`**

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ssdwtf import metrics
from ssdwtf.models import (DiskReport, HealthReport, ProcessReport, SmartReport,
                           StateDir, StateDirReport, SwapReport,
                           make_empty_report)


def _report(ts: str, swap_mb: float) -> HealthReport:
    rep = make_empty_report(ts, 64.0)
    rep.smart = SmartReport(available=True, percent_used=2, tb_written=54.0,
                            available_spare=100, media_errors=0)
    rep.swap = SwapReport(total_mb=1024.0, used_mb=swap_mb, free_mb=0.0)
    rep.disk = DiskReport(mount="/System/Volumes/Data", size_gb=994.6,
                          used_gb=500.0, avail_gb=412.6, pct_used=55.0,
                          pct_free=41.5)
    rep.processes = ProcessReport(ghosts=[], total_ide_processes=7)
    rep.statedirs = StateDirReport(
        dirs=[StateDir(key="cursor-vscdb", path="/x", exists=True,
                       size_bytes=int(0.5e9))], total_bytes=int(3e9))
    return rep


class TestMetrics(unittest.TestCase):
    def test_record_and_series_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            metrics.record(_report("2026-07-29T10:00:00", 512.0), path=db)
            metrics.record(_report("2026-07-30T10:00:00", 1024.0), path=db)
            vals = metrics.series("swap.used_gb", days=7, path=db)
            self.assertEqual(len(vals), 2)
            self.assertAlmostEqual(vals[-1][1], 1.0)

    def test_rate_per_day(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            metrics.record(_report("2026-07-28T10:00:00", 0.0), path=db)
            metrics.record(_report("2026-07-30T10:00:00", 2048.0), path=db)
            rate = metrics.rate_per_day("swap.used_gb", days=7, path=db)
            self.assertIsNotNone(rate)
            self.assertAlmostEqual(rate, 1.0, places=5)  # 2 GB over 2 days

    def test_rate_needs_two_points(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            self.assertIsNone(metrics.rate_per_day("swap.used_gb", 7, path=db))
            metrics.record(_report("2026-07-30T10:00:00", 512.0), path=db)
            self.assertIsNone(metrics.rate_per_day("swap.used_gb", 7, path=db))

    def test_unavailable_sources_record_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            rep = make_empty_report("2026-07-30T10:00:00", 64.0)
            metrics.record(rep, path=db)  # everything unavailable/None
            self.assertEqual(metrics.series("smart.percent_used", 7, path=db), [])
            self.assertIsNone(metrics.latest("smart.percent_used", path=db))

    def test_record_never_raises_on_bad_path(self):
        rep = _report("2026-07-30T10:00:00", 512.0)
        metrics.record(rep, path=Path("/nonexistent-dir-x/m.db"))  # no raise


if __name__ == "__main__":
    unittest.main()
```

Note: `test_record_never_raises_on_bad_path` may actually succeed on macOS if
`/nonexistent-dir-x` is creatable — it isn't (root of filesystem is read-only
for regular users on macOS), so `record` exercises its exception path. If it
unexpectedly creates the dir on some system, the test still passes (record
simply records).

- [ ] **Step 3: Run tests**

Run: `python3 -m unittest tests.test_metrics -v`
Expected: 5 tests, OK

- [ ] **Step 4: Commit**

```bash
git add ssdwtf/metrics.py tests/test_metrics.py
git commit -m "phase1: add sqlite metrics baseline store"
```

---

### Task 2: models.py + config.py extension (the additive contract edit)

**Files:**
- Modify: `ssdwtf/models.py` (additive only)
- Modify: `ssdwtf/config.py` (DEFAULTS additions)
- Test: `tests/test_models.py` (extend — add new tests, do not weaken existing)

**Interfaces:**
- Consumes: nothing new.
- Produces: dataclasses `PressureReport`, `SystemReport`, `ApfsReport`, `BackupReport`, `CrashReport`, `WriteRateReport`; `SmartReport` new fields `critical_warning`, `spare_threshold`, `unsafe_shutdowns`, `temperature_c`; `HealthReport` new fields `pressure`, `system`, `apfs`, `backup`, `crashes`, `writerate`, `external_smart`; `Finding.evidence`. Every collector/analyze/cli task after this one imports these names.

- [ ] **Step 1: Extend `ssdwtf/models.py`**

Add to `SmartReport` (after `tb_written`):

```python
    critical_warning: Optional[int] = None   # NVMe Critical Warning bitmask (0 = ok)
    spare_threshold: Optional[int] = None    # device-reported Available Spare Threshold %
    unsafe_shutdowns: Optional[int] = None
    temperature_c: Optional[int] = None      # composite temperature
```

Add to `Finding` (after `recommendation`):

```python
    evidence: str = "measured"  # measured|derived|correlated|inferred|reported|unavailable
```

Insert these new dataclasses after `StateDirReport`:

```python
@dataclass
class PressureReport:
    available: bool
    error: Optional[str] = None
    level: Optional[int] = None       # 1=normal, 2=warn, 4=critical (sysctl)
    free_pct: Optional[float] = None  # memory_pressure fallback


@dataclass
class SystemReport:
    available: bool
    error: Optional[str] = None
    uptime_days: Optional[float] = None
    cpu_speed_limit: Optional[int] = None  # 100 = not throttled
    battery_present: bool = False
    battery_cycle_count: Optional[int] = None
    battery_max_capacity_pct: Optional[int] = None


@dataclass
class ApfsReport:
    available: bool
    error: Optional[str] = None
    snapshot_count: int = 0
    oldest_snapshot_days: Optional[float] = None
    container_free_gb: Optional[float] = None
    volume_used_gb: Optional[float] = None


@dataclass
class BackupReport:
    available: bool
    error: Optional[str] = None
    configured: bool = False
    destination_present: bool = False
    last_backup_age_hours: Optional[float] = None
    destinations: list[str] = field(default_factory=list)


@dataclass
class CrashReport:
    available: bool
    error: Optional[str] = None
    weekly: dict[str, int] = field(default_factory=dict)
    total_weekly: int = 0


@dataclass
class WriteRateReport:
    available: bool
    error: Optional[str] = None
    mb_per_s: Optional[float] = None
```

Extend `HealthReport` (after `statedirs`):

```python
    pressure: PressureReport = field(default_factory=lambda: PressureReport(available=False))
    system: SystemReport = field(default_factory=lambda: SystemReport(available=False))
    apfs: ApfsReport = field(default_factory=lambda: ApfsReport(available=False))
    backup: BackupReport = field(default_factory=lambda: BackupReport(available=False))
    crashes: CrashReport = field(default_factory=lambda: CrashReport(available=False))
    writerate: WriteRateReport = field(default_factory=lambda: WriteRateReport(available=False))
    external_smart: list[SmartReport] = field(default_factory=list)
```

Extend `report_from_dict` — replace the final `return HealthReport(...)` with a
tolerant version (old JSONL rows lack the new keys; new rows from future
versions may carry unknown keys):

```python
def report_from_dict(d: dict[str, Any]) -> HealthReport:
    smart = SmartReport(**{k: v for k, v in d["smart"].items()
                           if k in SmartReport.__dataclass_fields__})
    swap = SwapReport(**d["swap"]) if d.get("swap") else None
    disk = DiskReport(**d["disk"]) if d.get("disk") else None
    procs = ProcessReport(
        ghosts=[GhostProcess(**g) for g in d["processes"].get("ghosts", [])],
        total_ide_processes=d["processes"].get("total_ide_processes", 0),
        note=d["processes"].get("note"),
    )
    statedirs = StateDirReport(
        dirs=[StateDir(**s) for s in d["statedirs"].get("dirs", [])],
        total_bytes=d["statedirs"].get("total_bytes", 0),
        note=d["statedirs"].get("note"),
    )

    def _sub(cls, key, default_available=False):
        raw = d.get(key)
        if not raw:
            return cls(available=default_available)
        return cls(**{k: v for k, v in raw.items()
                      if k in cls.__dataclass_fields__})

    external = [SmartReport(**{k: v for k, v in s.items()
                               if k in SmartReport.__dataclass_fields__})
                for s in d.get("external_smart", [])]
    return HealthReport(
        timestamp=d["timestamp"],
        host_ram_gb=d["host_ram_gb"],
        smart=smart,
        swap=swap,
        disk=disk,
        processes=procs,
        statedirs=statedirs,
        pressure=_sub(PressureReport, "pressure"),
        system=_sub(SystemReport, "system"),
        apfs=_sub(ApfsReport, "apfs"),
        backup=_sub(BackupReport, "backup"),
        crashes=_sub(CrashReport, "crashes"),
        writerate=_sub(WriteRateReport, "writerate"),
        external_smart=external,
    )
```

(Keep `report_to_dict` and `make_empty_report` unchanged — asdict and the
default factories cover the new fields.)

- [ ] **Step 2: Extend `ssdwtf/config.py` DEFAULTS**

Replace the `DEFAULTS` dict with:

```python
DEFAULTS: dict[str, Any] = {
    "swap": {"warn_gb": 8.0, "crit_gb": 16.0},
    "disk": {"warn_free_pct": 15.0, "crit_free_pct": 10.0,
             "mount": "/System/Volumes/Data"},
    "procs": {"ghost_days": 3.0, "warn_count": 20},
    "state": {"vscdb_warn_gb": 2.0, "growth_warn_gb_day": 1.0,
              "total_warn_gb": 20.0},
    "smart": {"device": "/dev/disk0", "writes_warn_gb_day": 300.0,
              "external_devices": []},
    "alerts": {"enabled": True, "cooldown_hours": 24.0},
    "watch": {"interval_minutes": 60},
    "clean": {"node_stale_days": 30, "caches_top_n": 10, "caches_min_mb": 500},
    "projects": [],
    "tiers": {"fast": ["smart", "swap", "disk", "processes", "pressure",
                       "system", "writerate"],
              "slow": ["statedirs", "apfs", "backup", "crashes"]},
    "pressure": {"sustained_min": 10},
    "apfs": {"snapshot_warn_days": 7},
    "backup": {"enabled": True, "warn_hours": 48, "crit_hours": 168},
    "crashes": {"warn_weekly": 3,
                "apps": ["Cursor", "Code", "Claude", "Windsurf"]},
    "thermal": {"warn_below": 100},
    "uptime": {"warn_days": 14},
    "writerate": {"device": "disk0", "warn_mb_s": 200},
    "battery": {"capacity_info_pct": 90},
}
```

- [ ] **Step 3: Extend `tests/test_models.py`**

Append a new test class (leave all existing tests untouched):

```python
class TestPhase1Models(unittest.TestCase):
    def test_new_reports_have_defaults(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        self.assertFalse(rep.pressure.available)
        self.assertFalse(rep.system.available)
        self.assertFalse(rep.apfs.available)
        self.assertFalse(rep.backup.available)
        self.assertFalse(rep.crashes.available)
        self.assertFalse(rep.writerate.available)
        self.assertEqual(rep.external_smart, [])

    def test_finding_evidence_defaults_measured(self):
        f = models.Finding(pillar="monitor", severity="info", code="x.y",
                           title="t", detail="d", recommendation="r")
        self.assertEqual(f.evidence, "measured")

    def test_smart_new_fields_default_none(self):
        s = models.SmartReport(available=True)
        self.assertIsNone(s.critical_warning)
        self.assertIsNone(s.spare_threshold)
        self.assertIsNone(s.unsafe_shutdowns)
        self.assertIsNone(s.temperature_c)

    def test_roundtrip_with_new_fields(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        rep.pressure = models.PressureReport(available=True, level=1, free_pct=70.0)
        rep.backup = models.BackupReport(available=True, configured=True,
                                         destination_present=False,
                                         last_backup_age_hours=None,
                                         destinations=["TM Backup"])
        d = models.report_to_dict(rep)
        back = models.report_from_dict(d)
        self.assertEqual(back.pressure.level, 1)
        self.assertTrue(back.backup.configured)
        self.assertEqual(back.backup.destinations, ["TM Backup"])

    def test_from_dict_tolerates_old_rows(self):
        # a v0.1.0 history row: no phase-1 keys at all
        rep = models.make_empty_report("2026-07-29T10:00:00", 64.0)
        d = models.report_to_dict(rep)
        for k in ("pressure", "system", "apfs", "backup", "crashes",
                  "writerate", "external_smart"):
            d.pop(k, None)
        back = models.report_from_dict(d)
        self.assertFalse(back.pressure.available)
        self.assertEqual(back.external_smart, [])


if __name__ == "__main__":
    unittest.main()
```

(The file already ends with `if __name__ == "__main__": unittest.main()` —
insert the new class before that block, do not duplicate it.)

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests.test_models tests.test_config -v`
Expected: all pass (existing + 4 new)

- [ ] **Step 5: Commit**

```bash
git add ssdwtf/models.py ssdwtf/config.py tests/test_models.py
git commit -m "phase1: additive models+config extension (new reports, evidence, tiers)"
```

---

### Task 3: Pressure collector

**Files:**
- Create: `ssdwtf/collectors/pressure.py`
- Test: `tests/test_pressure.py`
- Fixtures (already captured): `tests/fixtures/sysctl_pressure.txt` (contains `1`), `tests/fixtures/memory_pressure.txt`

**Interfaces:**
- Consumes: `._run.run_cmd`, `..models.PressureReport`.
- Produces: `parse_pressure_level(text) -> Optional[int]`, `parse_memory_pressure_free(text) -> Optional[float]`, `collect_pressure(runner=run_cmd) -> PressureReport`.

- [ ] **Step 1: Write `ssdwtf/collectors/pressure.py`**

```python
from __future__ import annotations

import re
from typing import Callable, Optional

from ..models import PressureReport
from ._run import run_cmd

_LEVEL_RE = re.compile(r"^\s*(\d+)\s*$")
_FREE_RE = re.compile(r"System-wide memory free percentage:\s*(\d+)%")


def parse_pressure_level(text: str) -> Optional[int]:
    m = _LEVEL_RE.match(text)
    return int(m.group(1)) if m else None


def parse_memory_pressure_free(text: str) -> Optional[float]:
    m = _FREE_RE.search(text)
    return float(m.group(1)) if m else None


def collect_pressure(runner: Callable = run_cmd) -> PressureReport:
    """Memory pressure: sysctl level primary, memory_pressure free-% as context."""
    out = runner(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"])
    if out is None:
        return PressureReport(available=False, error="sysctl unavailable")
    level = parse_pressure_level(out)
    if level is None:
        return PressureReport(available=False,
                              error=f"unparseable pressure level: {out.strip()[:40]}")
    free_pct = None
    mp = runner(["memory_pressure"])
    if mp is not None:
        free_pct = parse_memory_pressure_free(mp)
    return PressureReport(available=True, level=level, free_pct=free_pct)
```

- [ ] **Step 2: Write `tests/test_pressure.py`**

```python
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
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_pressure -v` → 5 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/pressure.py tests/test_pressure.py && git commit -m "phase1: memory pressure collector"`

---

### Task 4: System collector (uptime, throttle, battery)

**Files:**
- Create: `ssdwtf/collectors/system.py`
- Test: `tests/test_system.py`
- Fixtures (already captured): `tests/fixtures/sysctl_boottime.txt`, `tests/fixtures/pmset_therm.txt`, `tests/fixtures/ioreg_battery.txt`

**Interfaces:**
- Consumes: `._run.run_cmd`, `..models.SystemReport`.
- Produces: `parse_boot_time(text) -> Optional[int]`, `parse_cpu_speed_limit(text) -> int` (100 when absent), `parse_battery(text) -> tuple[Optional[int], Optional[int]]` (cycle_count, max_capacity), `collect_system(runner=run_cmd, now=None) -> SystemReport`.

- [ ] **Step 1: Write `ssdwtf/collectors/system.py`**

```python
from __future__ import annotations

import re
import time
from typing import Callable, Optional

from ..models import SystemReport
from ._run import run_cmd

_BOOT_RE = re.compile(r"sec\s*=\s*(\d+)")
_LIMIT_RE = re.compile(r"CPU_Speed_Limit\s*=\s*(\d+)")
# top-level ioreg keys have spaces around '='; nested BatteryData does not
_CYCLE_RE = re.compile(r'"CycleCount"\s+=\s+(\d+)')
_CAP_RE = re.compile(r'"MaxCapacity"\s+=\s+(\d+)')


def parse_boot_time(text: str) -> Optional[int]:
    m = _BOOT_RE.search(text)
    return int(m.group(1)) if m else None


def parse_cpu_speed_limit(text: str) -> int:
    """pmset -g therm → current CPU speed limit %. 100 = not throttled;
    the 'No ... recorded' notes mean no limit is in effect."""
    m = _LIMIT_RE.search(text)
    return int(m.group(1)) if m else 100


def parse_battery(text: str) -> tuple[Optional[int], Optional[int]]:
    cycle = _CYCLE_RE.search(text)
    cap = _CAP_RE.search(text)
    return (int(cycle.group(1)) if cycle else None,
            int(cap.group(1)) if cap else None)


def collect_system(runner: Callable = run_cmd,
                   now: Optional[float] = None) -> SystemReport:
    """Uptime (kern.boottime), thermal throttle state (pmset), battery (ioreg).
    Degrades per-source: a laptop-less Mac simply reports battery_present=False."""
    now = time.time() if now is None else now
    rep = SystemReport(available=True)

    out = runner(["sysctl", "kern.boottime"])
    boot = parse_boot_time(out) if out else None
    rep.uptime_days = round((now - boot) / 86400.0, 2) if boot else None

    therm = runner(["pmset", "-g", "therm"])
    rep.cpu_speed_limit = parse_cpu_speed_limit(therm) if therm else None

    bat = runner(["ioreg", "-rn", "AppleSmartBattery"])
    if bat:
        cycle, cap = parse_battery(bat)
        rep.battery_present = cycle is not None or cap is not None
        rep.battery_cycle_count = cycle
        rep.battery_max_capacity_pct = cap

    if rep.uptime_days is None and rep.cpu_speed_limit is None:
        return SystemReport(available=False, error="sysctl/pmset unavailable")
    return rep
```

- [ ] **Step 2: Write `tests/test_system.py`**

```python
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
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_system -v` → 6 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/system.py tests/test_system.py && git commit -m "phase1: system collector (uptime/throttle/battery)"`

---

### Task 5: APFS collector (local snapshots + container space)

**Files:**
- Create: `ssdwtf/collectors/apfs.py`
- Test: `tests/test_apfs.py`
- Fixtures (already captured): `tests/fixtures/tmutil_snapshots.txt` (header only, zero snapshots), `tests/fixtures/diskutil_info.txt` (Data volume)

**Interfaces:**
- Consumes: `._run.run_cmd`, `..models.ApfsReport`, config `disk.mount`.
- Produces: `parse_snapshot_names(text) -> list[str]`, `snapshot_age_days(name, now) -> Optional[float]`, `parse_diskutil_info(text) -> dict`, `collect_apfs(mount, runner=run_cmd, now=None) -> ApfsReport`.

- [ ] **Step 1: Write `ssdwtf/collectors/apfs.py`**

```python
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Callable, Optional

from ..models import ApfsReport
from ._run import run_cmd

_SNAP_RE = re.compile(r"^com\.apple\.TimeMachine\.\d{4}-\d{2}-\d{2}-\d{6}")
_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})-(\d{6})")
_BYTES_RE = re.compile(r"\((\d+) Bytes\)")


def parse_snapshot_names(text: str) -> list[str]:
    """tmutil listlocalsnapshots / → snapshot names (header line excluded)."""
    return [line.strip() for line in text.splitlines()
            if _SNAP_RE.match(line.strip())]


def snapshot_age_days(name: str, now: Optional[float] = None) -> Optional[float]:
    m = _DATE_RE.search(name)
    if not m:
        return None
    now = time.time() if now is None else now
    try:
        dt = datetime.strptime(m.group(0), "%Y-%m-%d-%H%M%S")
    except ValueError:
        return None
    return (now - dt.timestamp()) / 86400.0


def parse_diskutil_info(text: str) -> dict:
    """diskutil info <mount> → {'container_free_gb': f, 'volume_used_gb': f}."""
    out: dict[str, float] = {}
    for line in text.splitlines():
        stripped = line.strip()
        m = _BYTES_RE.search(stripped)
        if not m:
            continue
        gb = int(m.group(1)) / 1e9
        if stripped.startswith("Container Free Space:"):
            out["container_free_gb"] = gb
        elif stripped.startswith("Volume Used Space:"):
            out["volume_used_gb"] = gb
    return out


def collect_apfs(mount: str, runner: Callable = run_cmd,
                 now: Optional[float] = None) -> ApfsReport:
    snap_out = runner(["tmutil", "listlocalsnapshots", "/"])
    info_out = runner(["diskutil", "info", mount])
    if snap_out is None and info_out is None:
        return ApfsReport(available=False, error="tmutil/diskutil unavailable")

    rep = ApfsReport(available=True)
    if snap_out is not None:
        names = parse_snapshot_names(snap_out)
        rep.snapshot_count = len(names)
        ages = [a for a in (snapshot_age_days(n, now) for n in names)
                if a is not None]
        rep.oldest_snapshot_days = round(max(ages), 2) if ages else None
    else:
        rep.error = "tmutil listlocalsnapshots failed"
    if info_out is not None:
        info = parse_diskutil_info(info_out)
        rep.container_free_gb = info.get("container_free_gb")
        rep.volume_used_gb = info.get("volume_used_gb")
    return rep
```

- [ ] **Step 2: Write `tests/test_apfs.py`**

```python
from __future__ import annotations

import unittest
from pathlib import Path

from ssdwtf.collectors import apfs

FIX = Path(__file__).parent / "fixtures"


def _runner(cmd):
    if "listlocalsnapshots" in cmd:
        return (FIX / "tmutil_snapshots.txt").read_text()
    if cmd[:1] == ["diskutil"]:
        return (FIX / "diskutil_info.txt").read_text()
    return None


class TestApfs(unittest.TestCase):
    def test_parse_names_empty(self):
        text = (FIX / "tmutil_snapshots.txt").read_text()
        self.assertEqual(apfs.parse_snapshot_names(text), [])

    def test_parse_names_multi(self):
        text = ("Snapshots for disk /:\n"
                "com.apple.TimeMachine.2026-07-20-090001\n"
                "com.apple.TimeMachine.2026-07-28-113002\n")
        self.assertEqual(len(apfs.parse_snapshot_names(text)), 2)

    def test_snapshot_age(self):
        import datetime as dt
        now = dt.datetime(2026, 7, 30, 12, 0, 0).timestamp()
        age = apfs.snapshot_age_days(
            "com.apple.TimeMachine.2026-07-20-120000", now)
        self.assertIsNotNone(age)
        self.assertAlmostEqual(age, 10.0, places=1)
        self.assertIsNone(apfs.snapshot_age_days("no-date-here", now))

    def test_parse_diskutil_info(self):
        text = (FIX / "diskutil_info.txt").read_text()
        info = apfs.parse_diskutil_info(text)
        self.assertAlmostEqual(info["container_free_gb"], 412.6, places=0)
        self.assertAlmostEqual(info["volume_used_gb"], 558.4, places=0)

    def test_collect_real_fixtures(self):
        rep = apfs.collect_apfs("/System/Volumes/Data", runner=_runner)
        self.assertTrue(rep.available)
        self.assertEqual(rep.snapshot_count, 0)
        self.assertIsNone(rep.oldest_snapshot_days)
        self.assertAlmostEqual(rep.container_free_gb, 412.6, places=0)

    def test_collect_degrades(self):
        rep = apfs.collect_apfs("/System/Volumes/Data",
                                runner=lambda cmd: None)
        self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_apfs -v` → 6 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/apfs.py tests/test_apfs.py && git commit -m "phase1: apfs collector (local snapshots, container space)"`

---

### Task 6: Backup readiness collector (Time Machine)

**Files:**
- Create: `ssdwtf/collectors/backup.py`
- Test: `tests/test_backup.py`
- Fixtures (already captured): `tests/fixtures/tmutil_destinations.txt` (1 destination, Local kind, unmounted), `tests/fixtures/tmutil_latestbackup.txt` (mount failure message — the degraded real case)

**Interfaces:**
- Consumes: `._run.run_cmd`, `..models.BackupReport`.
- Produces: `parse_destinationinfo(text) -> list[str]` (destination names), `parse_latest_backup_date(text) -> Optional[str]` (YYYY-MM-DD-HHMMSS), `collect_backup(runner=run_cmd, now=None) -> BackupReport`.

- [ ] **Step 1: Write `ssdwtf/collectors/backup.py`**

```python
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Callable, Optional

from ..models import BackupReport
from ._run import run_cmd

_NAME_RE = re.compile(r"^Name\s*:\s*(.+)$", re.MULTILINE)
_MOUNT_RE = re.compile(r"^(?:Mount Point|URL)\s*:\s*(.+)$", re.MULTILINE)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}-\d{6})")


def parse_destinationinfo(text: str) -> list[str]:
    return [m.strip() for m in _NAME_RE.findall(text)]


def parse_latest_backup_date(text: str) -> Optional[str]:
    """tmutil latestbackup prints a path ending in .../YYYY-MM-DD-HHMMSS[.backup];
    failure messages contain no such date."""
    m = _DATE_RE.search(text)
    return m.group(1) if m else None


def collect_backup(runner: Callable = run_cmd,
                   now: Optional[float] = None) -> BackupReport:
    """Time Machine readiness. available=False only when tmutil itself fails."""
    now = time.time() if now is None else now
    dest_out = runner(["tmutil", "destinationinfo"])
    if dest_out is None:
        return BackupReport(available=False, error="tmutil unavailable")

    destinations = parse_destinationinfo(dest_out)
    rep = BackupReport(available=True, configured=bool(destinations),
                       destinations=destinations)
    rep.destination_present = bool(_MOUNT_RE.search(dest_out))

    latest_out = runner(["tmutil", "latestbackup"])
    if latest_out is not None:
        date_str = parse_latest_backup_date(latest_out)
        if date_str:
            rep.destination_present = True  # a completed backup implies access
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d-%H%M%S")
                rep.last_backup_age_hours = round(
                    (now - dt.timestamp()) / 3600.0, 1)
            except ValueError:
                pass
    return rep
```

- [ ] **Step 2: Write `tests/test_backup.py`**

```python
from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path

from ssdwtf.collectors import backup

FIX = Path(__file__).parent / "fixtures"
NOW = dt.datetime(2026, 7, 30, 12, 0, 0).timestamp()


def _runner_real(cmd):
    if "destinationinfo" in cmd:
        return (FIX / "tmutil_destinations.txt").read_text()
    if "latestbackup" in cmd:
        return (FIX / "tmutil_latestbackup.txt").read_text()  # mount failure
    return None


def _runner_healthy(cmd):
    if "destinationinfo" in cmd:
        return ("====================================================\n"
                "Name          : MOGD28TB\n"
                "Kind          : Local\n"
                "Mount Point   : /Volumes/MOGD28TB\n"
                "ID            : X\n")
    if "latestbackup" in cmd:
        return "/Volumes/MOGD28TB/Backups.backupdb/mac/2026-07-29-120000\n"
    return None


class TestBackup(unittest.TestCase):
    def test_parse_destinations(self):
        text = (FIX / "tmutil_destinations.txt").read_text()
        self.assertEqual(backup.parse_destinationinfo(text),
                         ["TM_05-31-26_to_0"])

    def test_parse_latest_date(self):
        self.assertEqual(
            backup.parse_latest_backup_date(
                "/Volumes/X/Backups.backupdb/m/2026-07-29-120000\n"),
            "2026-07-29-120000")
        self.assertIsNone(backup.parse_latest_backup_date(
            "Failed to mount backup destination, error: ..."))

    def test_collect_degraded_real_fixture(self):
        rep = backup.collect_backup(runner=_runner_real, now=NOW)
        self.assertTrue(rep.available)
        self.assertTrue(rep.configured)
        self.assertFalse(rep.destination_present)
        self.assertIsNone(rep.last_backup_age_hours)

    def test_collect_healthy(self):
        rep = backup.collect_backup(runner=_runner_healthy, now=NOW)
        self.assertTrue(rep.destination_present)
        self.assertAlmostEqual(rep.last_backup_age_hours, 24.0, places=1)

    def test_collect_not_configured(self):
        rep = backup.collect_backup(
            runner=lambda cmd: "" if "tmutil" in cmd else None, now=NOW)
        self.assertTrue(rep.available)
        self.assertFalse(rep.configured)

    def test_collect_degrades(self):
        rep = backup.collect_backup(runner=lambda cmd: None)
        self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_backup -v` → 6 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/backup.py tests/test_backup.py && git commit -m "phase1: time machine readiness collector"`

---

### Task 7: Crash-frequency collector

**Files:**
- Create: `ssdwtf/collectors/crashes.py`
- Test: `tests/test_crashes.py`

**Interfaces:**
- Consumes: `..models.CrashReport`. Pure filesystem (statedirs pattern — no runner).
- Produces: `collect_crashes(apps, dir=None, now=None) -> CrashReport`, `app_from_filename(name) -> str`.

macOS crash reports live at `~/Library/Logs/DiagnosticReports/<App>-YYYY-MM-DD-HHMMSS.ips`
(also `.crash`, and names may contain spaces, e.g. `Claude Helper-...`).

- [ ] **Step 1: Write `ssdwtf/collectors/crashes.py`**

```python
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

from ..models import CrashReport

# Cursor-2026-07-29-123456.ips / Claude Helper-2026-07-29-010203.crash
_NAME_RE = re.compile(r"^(.+?)-\d{4}-\d{2}-\d{2}-\d{6}\.(?:ips|crash)$")
_WEEK_S = 7 * 86400


def app_from_filename(name: str) -> Optional[str]:
    m = _NAME_RE.match(name)
    return m.group(1) if m else None


def collect_crashes(apps: list[str], dir: Optional[Path] = None,
                    now: Optional[float] = None) -> CrashReport:
    """Count DiagnosticReports per watched app over the trailing 7 days.
    Never raises; a missing reports dir just means zero crashes."""
    now = time.time() if now is None else now
    reports_dir = dir or (Path.home() / "Library" / "Logs" / "DiagnosticReports")
    weekly: dict[str, int] = {a: 0 for a in apps}
    if not reports_dir.is_dir():
        return CrashReport(available=True, weekly=weekly, total_weekly=0)
    watched = {a.lower(): a for a in apps}
    try:
        entries = list(reports_dir.iterdir())
    except OSError as exc:
        return CrashReport(available=False, error=str(exc))
    for entry in entries:
        app = app_from_filename(entry.name)
        if app is None:
            continue
        canonical = watched.get(app.lower())
        if canonical is None:
            continue
        try:
            if now - entry.stat().st_mtime > _WEEK_S:
                continue
        except OSError:
            continue
        weekly[canonical] += 1
    return CrashReport(available=True, weekly=weekly,
                       total_weekly=sum(weekly.values()))
```

- [ ] **Step 2: Write `tests/test_crashes.py`**

```python
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ssdwtf.collectors import crashes

NOW = 1_785_500_000.0
APPS = ["Cursor", "Claude"]


def _make(dir: Path, name: str, age_days: float) -> None:
    p = dir / name
    p.write_text("{}")
    os.utime(p, (NOW - age_days * 86400, NOW - age_days * 86400))


class TestCrashes(unittest.TestCase):
    def test_app_from_filename(self):
        self.assertEqual(crashes.app_from_filename(
            "Cursor-2026-07-29-123456.ips"), "Cursor")
        self.assertEqual(crashes.app_from_filename(
            "Claude Helper-2026-07-29-010203.crash"), "Claude Helper")
        self.assertIsNone(crashes.app_from_filename("random.txt"))
        self.assertIsNone(crashes.app_from_filename("Cursor.ips"))

    def test_counts_recent_only(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _make(d, "Cursor-2026-07-29-123456.ips", 1)
            _make(d, "Cursor-2026-07-28-123456.ips", 3)
            _make(d, "Cursor-2026-07-20-123456.ips", 30)  # too old
            _make(d, "Claude-2026-07-29-123456.ips", 2)
            _make(d, "Safari-2026-07-29-123456.ips", 1)   # not watched
            rep = crashes.collect_crashes(APPS, dir=d, now=NOW)
            self.assertTrue(rep.available)
            self.assertEqual(rep.weekly, {"Cursor": 2, "Claude": 1})
            self.assertEqual(rep.total_weekly, 3)

    def test_missing_dir_is_zero_not_error(self):
        rep = crashes.collect_crashes(
            APPS, dir=Path("/nonexistent-diag-x"), now=NOW)
        self.assertTrue(rep.available)
        self.assertEqual(rep.total_weekly, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_crashes -v` → 3 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/crashes.py tests/test_crashes.py && git commit -m "phase1: crash frequency collector"`

---

### Task 8: Write-rate collector (iostat)

**Files:**
- Create: `ssdwtf/collectors/writerate.py`
- Test: `tests/test_writerate.py`
- Fixture (already captured): `tests/fixtures/iostat.txt` (header + 2 samples; second sample is the live rate)

**Interfaces:**
- Consumes: `._run.run_cmd`, `..models.WriteRateReport`, config `writerate.device`.
- Produces: `parse_iostat(text) -> Optional[float]`, `collect_writerate(device, runner=run_cmd) -> WriteRateReport`.

- [ ] **Step 1: Write `ssdwtf/collectors/writerate.py`**

```python
from __future__ import annotations

from typing import Callable, Optional

from ..models import WriteRateReport
from ._run import run_cmd


def parse_iostat(text: str) -> Optional[float]:
    """iostat -d -w 1 -c 2 <dev> → MB/s from the LAST sample row.
    Rows are: KB/t tps MB/s (three floats). The first row is the
    since-boot average; the last is the current interval rate."""
    rows: list[list[str]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3:
            try:
                [float(p) for p in parts]
            except ValueError:
                continue
            rows.append(parts)
    if not rows:
        return None
    return float(rows[-1][2])


def collect_writerate(device: str,
                      runner: Callable = run_cmd) -> WriteRateReport:
    out = runner(["iostat", "-d", "-w", "1", "-c", "2", device])
    if out is None:
        return WriteRateReport(available=False, error="iostat unavailable")
    rate = parse_iostat(out)
    if rate is None:
        return WriteRateReport(available=False,
                               error=f"unparseable iostat output for {device}")
    return WriteRateReport(available=True, mb_per_s=rate)
```

- [ ] **Step 2: Write `tests/test_writerate.py`**

```python
from __future__ import annotations

import unittest
from pathlib import Path

from ssdwtf.collectors import writerate

FIX = Path(__file__).parent / "fixtures"


class TestWriteRate(unittest.TestCase):
    def test_parse_real_fixture(self):
        text = (FIX / "iostat.txt").read_text()
        # fixture samples: 6.52 (since-boot avg) then 1.33 (interval)
        self.assertEqual(writerate.parse_iostat(text), 1.33)

    def test_parse_garbage(self):
        self.assertIsNone(writerate.parse_iostat("no data here"))
        self.assertIsNone(writerate.parse_iostat(""))

    def test_collect(self):
        rep = writerate.collect_writerate(
            "disk0", runner=lambda cmd: (FIX / "iostat.txt").read_text())
        self.assertTrue(rep.available)
        self.assertEqual(rep.mb_per_s, 1.33)

    def test_collect_degrades(self):
        rep = writerate.collect_writerate("disk0", runner=lambda cmd: None)
        self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_writerate -v` → 4 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/writerate.py tests/test_writerate.py && git commit -m "phase1: iostat write-rate collector"`

---

### Task 9: smart.py extension + external-drive collector

**Files:**
- Modify: `ssdwtf/collectors/smart.py` (extend parser — additive)
- Create: `ssdwtf/collectors/smartext.py`
- Test: `tests/test_smartext.py`; existing `tests/test_smart.py` must pass unmodified
- Fixture (already created): `tests/fixtures/smartctl_external.txt`

**Interfaces:**
- Consumes: `..models.SmartReport` (new fields from Task 2), existing `smart.parse_smartctl`.
- Produces: extended `parse_smartctl` filling `critical_warning`, `spare_threshold`, `unsafe_shutdowns`, `temperature_c`; `smartext.collect_smart_external(device, runner=run_cmd) -> SmartReport`.

- [ ] **Step 1: Extend `ssdwtf/collectors/smart.py`**

First read the current file. In `parse_smartctl`, after the existing field
extraction, add (using the same `_search_int` helper style already in the
module):

```python
    rep.critical_warning = _search_hex(text, r"Critical Warning:\s*(0x[0-9A-Fa-f]+)")
    rep.spare_threshold = _search_int(text, r"Available Spare Threshold:\s*(\d+)%")
    rep.unsafe_shutdowns = _search_int(text, r"Unsafe Shutdowns:\s*([\d,]+)")
    rep.temperature_c = _search_int(text, r"^Temperature:\s*(\d+)\s*Celsius")
```

Add the hex helper next to the existing `_search_int`:

```python
def _search_hex(text: str, pattern: str) -> Optional[int]:
    m = re.search(pattern, text, re.MULTILINE)
    return int(m.group(1), 16) if m else None
```

Note: `_search_int` in the current module strips commas before converting —
verify and reuse that behavior for `Unsafe Shutdowns`; if it does not strip
commas, handle `[\d,]+` with `int(m.group(1).replace(",", ""))` inside a
local parse. `Temperature:` must use MULTILINE anchoring (`^`) because NVMe
output also contains `Temperature Sensor 1:` lines on some drives — the
plain `Temperature:` row is the composite.

- [ ] **Step 2: Write `ssdwtf/collectors/smartext.py`**

```python
from __future__ import annotations

from typing import Callable

from ..models import SmartReport
from ._run import run_cmd
from .smart import parse_smartctl

_BRIDGES = ("auto", "sat")  # USB NVMe bridges usually need -d sat


def collect_smart_external(device: str,
                           runner: Callable = run_cmd) -> SmartReport:
    """SMART for an external drive, trying bridge protocols in order.
    available=False means: device absent, bridge unsupported, or smartctl
    missing — an unmounted/unplugged archive drive is data, not a crash."""
    for bridge in _BRIDGES:
        out = runner(["smartctl", "-a", "-d", bridge, device])
        if out is None:
            continue
        rep = parse_smartctl(out)
        if rep.model or rep.health:
            return rep
    return SmartReport(
        available=False,
        error=f"no SMART data from {device} (absent or unsupported bridge)")
```

- [ ] **Step 3: Write `tests/test_smartext.py`**

```python
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
```

- [ ] **Step 4: Run tests** — `python3 -m unittest tests.test_smartext tests.test_smart -v` → all OK (5 existing smart tests + 5 new)
- [ ] **Step 5: Commit** — `git add ssdwtf/collectors/smart.py ssdwtf/collectors/smartext.py tests/test_smartext.py && git commit -m "phase1: NVMe warning fields + external drive SMART"`

---

### Task 10: analyze.py — new findings + domain dashboard

**Files:**
- Modify: `ssdwtf/analyze.py` (additive: new findings, `domain_statuses`; signature of `analyze` unchanged)
- Test: `tests/test_analyze.py` (extend — add new test class, do not weaken existing)

**Interfaces:**
- Consumes: all Task 2 models, all Task 3–9 collectors' report shapes, config keys from Task 2.
- Produces: `DOMAINS: tuple[str, ...]`, `domain_statuses(findings, report) -> dict[str, str]` (values `ok|warn|critical|unknown`), new finding codes (below). Task 11 renders both.

Rules:
- New findings fire ONLY when their source report is `available` — existing
  tests build HealthReports without phase-1 fields (all unavailable), so
  `analyze` output on pre-phase-1 reports is unchanged.
- Read new config keys defensively: `config.get("backup", {})` etc., with
  the Task-2 DEFAULTS values as inline fallbacks.

- [ ] **Step 1: Extend `ssdwtf/analyze.py`**

Add after the existing imports:

```python
DOMAINS: tuple[str, ...] = ("drive", "backup", "headroom", "memory",
                            "processes", "state", "stability", "telemetry")

_DOMAIN_BY_PREFIX = {
    "smart.": "drive",
    "backup.": "backup",
    "disk.": "headroom", "apfs.": "headroom",
    "swap.": "memory", "pressure.": "memory", "memory.": "memory",
    "procs.": "processes",
    "state.": "state",
    "crashes.": "stability", "thermal.": "stability", "uptime.": "stability",
    "writerate.": "telemetry", "battery.": "telemetry",
}
```

Extend the SMART section (inside `else:` after the health check) — replace
the old spare rule and add the warning-bitmask rule:

```python
        # NVMe Critical Warning bitmask is the emergency channel (spec §4).
        if (smart.critical_warning or 0) != 0:
            findings.append(_f("monitor", "critical", "smart.critical_warning",
                f"Drive Critical Warning: 0x{smart.critical_warning:02x}",
                "The NVMe controller is reporting a reliability, temperature, or read-only condition.",
                "Back up now. Run `smartctl -a /dev/disk0` for the full log."))
        # Spare is only critical below the DEVICE'S OWN threshold — a drop
        # from 100% is normal aging, not an emergency (research §2).
        if (smart.available_spare is not None
                and smart.spare_threshold is not None
                and smart.available_spare < smart.spare_threshold):
            findings.append(_f("monitor", "critical", "smart.spare_low",
                f"Available spare {smart.available_spare}% below device threshold {smart.spare_threshold}%",
                "The controller is running out of replacement blocks.",
                "Back up now and monitor wear weekly."))
```

(Delete the old unconditional `available_spare < 100` critical. Existing
`tests/test_analyze.py` may assert on `smart.spare_low` behavior — check:
if an existing test constructs a report with `available_spare=90` and
expects critical, that test encodes the old rule; update THAT test to set
`spare_threshold=100` (keeping the assertion) or to expect no spare finding,
and note the change in your report. This is the one sanctioned existing-test
edit in this task.)

Append the new finding blocks at the end of `analyze` (before `return findings`):

```python
    # --- Backup readiness (its own domain: a green SSD never hides a red backup) ---
    bu = report.backup
    cfg_backup = config.get("backup", {})
    if bu.available and cfg_backup.get("enabled", True):
        if not bu.configured:
            findings.append(_f("monitor", "critical", "backup.none_configured",
                "No Time Machine destination configured",
                "The SSD is soldered to the logic board; local snapshots do not survive board failure.",
                "System Settings → Time Machine → add a destination."))
        else:
            if not bu.destination_present:
                findings.append(_f("monitor", "warn", "backup.destination_missing",
                    "Backup destination not mounted",
                    f"Configured: {', '.join(bu.destinations) or 'unknown'} — backups are not running.",
                    "Connect the backup drive."))
            age = bu.last_backup_age_hours
            if age is not None:
                if age >= cfg_backup.get("crit_hours", 168):
                    findings.append(_f("monitor", "critical", "backup.stale",
                        f"Last successful backup {age / 24:.0f} days ago",
                        "Restore readiness decays silently; this is the actual disaster domain.",
                        "Connect the backup drive and let a backup complete."))
                elif age >= cfg_backup.get("warn_hours", 48):
                    findings.append(_f("monitor", "warn", "backup.stale",
                        f"Last successful backup {age:.0f} h ago",
                        "Backups are falling behind.",
                        "Connect the backup drive."))

    # --- APFS local snapshots ---
    ap = report.apfs
    cfg_apfs = config.get("apfs", {})
    if ap.available and ap.oldest_snapshot_days is not None:
        days = cfg_apfs.get("snapshot_warn_days", 7)
        if ap.oldest_snapshot_days >= days:
            findings.append(_f("monitor", "warn", "apfs.snapshots_old",
                f"Local APFS snapshot {ap.oldest_snapshot_days:.0f} days old ({ap.snapshot_count} total)",
                "Local snapshots hold deleted blocks hostage — space you freed may not come back until they purge.",
                "`tmutil listlocalsnapshots /`; thin with `tmutil thinlocalsnapshots /` if space is tight."))

    # --- Memory pressure ---
    pr = report.pressure
    if pr.available and pr.level is not None:
        if pr.level >= 4:
            findings.append(_f("monitor", "critical", "pressure.critical",
                "Memory pressure CRITICAL",
                "The kernel is under extreme memory pressure; Apple Silicon masks it as silent thrashing.",
                "Quit memory-heavy apps; check ghost processes below."))
        elif pr.level >= 2:
            findings.append(_f("monitor", "warn", "pressure.warn",
                "Memory pressure elevated",
                f"Pressure level {pr.level} with {pr.free_pct:.0f}% free"
                if pr.free_pct is not None else f"Pressure level {pr.level}",
                "Watch for swap growth; consider closing unused IDE windows."))

    # --- Swap trend (derived from history) + thrash hint + restart hint ---
    swap_rate = _swap_rate_gb_day(history)
    if (swap_rate is not None and swap_rate > 0.5
            and pr.available and (pr.level or 1) >= 2):
        findings.append(_f("monitor", "warn", "memory.thrash_hint",
            f"Swap growing ~{swap_rate:.1f} GB/day under elevated pressure",
            "Growing swap plus kernel pressure is the thrash pattern — the #1 SSD write driver.",
            "Fully quit (Cmd+Q) agentic IDEs, or restart to drain swap."))
    sy = report.system
    cfg_up = config.get("uptime", {})
    if (sy.available and sy.uptime_days is not None and report.swap is not None
            and sy.uptime_days >= cfg_up.get("warn_days", 14)
            and report.swap.used_mb / 1024 >= config["swap"]["warn_gb"]):
        findings.append(_f("monitor", "warn", "uptime.restart_hint",
            f"Uptime {sy.uptime_days:.0f} days with {report.swap.used_mb / 1024:.1f} GB swap",
            "A restart drains swap — the cheapest recovery there is.",
            "Restart when convenient."))

    # --- Throttle / battery / writerate ---
    cfg_th = config.get("thermal", {})
    if (sy.available and sy.cpu_speed_limit is not None
            and sy.cpu_speed_limit < cfg_th.get("warn_below", 100)):
        findings.append(_f("monitor", "warn", "thermal.throttling",
            f"CPU throttled to {sy.cpu_speed_limit}%",
            "Thermal or power limits are cutting compute — correlate with swap/write storms.",
            "Check ventilation and what's driving the load."))
    cfg_bat = config.get("battery", {})
    if (sy.available and sy.battery_present
            and sy.battery_max_capacity_pct is not None
            and sy.battery_max_capacity_pct < cfg_bat.get("capacity_info_pct", 90)):
        findings.append(_f("monitor", "info", "battery.wear",
            f"Battery max capacity {sy.battery_max_capacity_pct}% ({sy.battery_cycle_count} cycles)",
            "Sustained agent workloads accelerate cycle burn; tracked monthly.",
            "Nothing to do — informational."))
    wr = report.writerate
    cfg_wr = config.get("writerate", {})
    if (wr.available and wr.mb_per_s is not None
            and wr.mb_per_s >= cfg_wr.get("warn_mb_s", 200)):
        findings.append(_f("monitor", "warn", "writerate.storm",
            f"Write rate {wr.mb_per_s:.0f} MB/s right now",
            "Sustained storms are usually indexing loops or snapshot churn.",
            "Check Activity Monitor's Disk tab for the culprit."))

    # --- Crash frequency ---
    cr = report.crashes
    cfg_cr = config.get("crashes", {})
    if cr.available:
        limit = cfg_cr.get("warn_weekly", 3)
        for app, count in cr.weekly.items():
            if count > limit:
                findings.append(_f("monitor", "warn", "crashes.frequent",
                    f"{app} crashed {count}× in 7 days",
                    "Mid-run crashes destroy agent context; frequent crashes signal resource exhaustion.",
                    f"Check ~/Library/Logs/DiagnosticReports for {app} reports."))
                break  # one finding is enough

    # --- External drives ---
    for ext in report.external_smart:
        if not ext.available:
            continue
        if ((ext.health and ext.health != "PASSED")
                or (ext.media_errors or 0) > 0
                or (ext.critical_warning or 0) != 0):
            findings.append(_f("monitor", "critical", "smart.external_unhealthy",
                f"External drive {ext.model or 'unknown'} unhealthy",
                f"health {ext.health or '?'} · media errors {ext.media_errors} · "
                f"critical warning 0x{(ext.critical_warning or 0):02x}",
                "This is your archive — verify backups and replace the drive."))
```

Add the two helpers at module level (end of file):

```python
def _swap_rate_gb_day(history: list[HealthReport]) -> float | None:
    """Least-squares slope of swap used (GB/day) across history entries."""
    pts: list[tuple[float, float]] = []
    for r in history:
        if r.swap is None:
            continue
        try:
            t = datetime.fromisoformat(r.timestamp).timestamp() / 86400.0
        except ValueError:
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


def domain_statuses(findings: list[Finding],
                    report: HealthReport) -> dict[str, str]:
    """Per-domain ok|warn|critical|unknown. unknown = no findings AND the
    domain's collectors were unavailable (never confuse absence of data
    with absence of problems)."""
    collector_ok = {
        "drive": report.smart.available,
        "backup": report.backup.available,
        "headroom": report.disk is not None or report.apfs.available,
        "memory": report.swap is not None or report.pressure.available,
        "processes": not report.processes.note,
        "state": bool(report.statedirs.dirs),
        "stability": report.crashes.available or report.system.available,
        "telemetry": report.writerate.available or report.system.available,
    }
    rank = {"ok": 0, "warn": 1, "critical": 2}
    out: dict[str, str] = {}
    for domain in DOMAINS:
        worst = "ok"
        for f in findings:
            for prefix, d in _DOMAIN_BY_PREFIX.items():
                if f.code.startswith(prefix) and d == domain:
                    sev = f.severity if f.severity in rank else "ok"
                    if rank[sev] > rank[worst]:
                        worst = sev
        if worst == "ok" and not collector_ok.get(domain, True):
            worst = "unknown"
        out[domain] = worst
    return out
```

(`datetime` and `Finding` are already imported in analyze.py; add
`from datetime import datetime` at the top if only the lazy Task-7 import
exists — move it to the top-level imports and remove the lazy one inside
the monthly-check block, keeping that block's behavior identical.)

- [ ] **Step 2: Extend `tests/test_analyze.py`**

Append (before the `if __name__` block), adapting the file's existing
report-builder helpers if it has them:

```python
def _base_report() -> models.HealthReport:
    rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
    rep.swap = models.SwapReport(total_mb=1024.0, used_mb=0.0, free_mb=0.0)
    return rep


class TestPhase1Findings(unittest.TestCase):
    def _codes(self, rep, cfg=None):
        findings = analyze.analyze(rep, [], cfg or dict(DEFAULTS))
        return {f.code for f in findings}

    def test_backup_none_configured_is_critical(self):
        rep = _base_report()
        rep.backup = models.BackupReport(available=True, configured=False)
        codes = self._codes(rep)
        self.assertIn("backup.none_configured", codes)

    def test_backup_stale_warn_and_crit(self):
        rep = _base_report()
        rep.backup = models.BackupReport(available=True, configured=True,
                                         destination_present=True,
                                         last_backup_age_hours=72.0)
        self.assertIn("backup.stale", self._codes(rep))
        rep.backup = models.BackupReport(available=True, configured=True,
                                         destination_present=True,
                                         last_backup_age_hours=200.0)
        crit = [f for f in analyze.analyze(rep, [], dict(DEFAULTS))
                if f.code == "backup.stale"]
        self.assertEqual(crit[0].severity, "critical")

    def test_unavailable_backup_fires_nothing(self):
        rep = _base_report()  # backup defaults to available=False
        self.assertNotIn("backup.none_configured", self._codes(rep))

    def test_pressure_levels(self):
        rep = _base_report()
        rep.pressure = models.PressureReport(available=True, level=4)
        self.assertIn("pressure.critical", self._codes(rep))
        rep.pressure = models.PressureReport(available=True, level=2,
                                             free_pct=15.0)
        self.assertIn("pressure.warn", self._codes(rep))

    def test_spare_uses_device_threshold(self):
        rep = _base_report()
        rep.smart = models.SmartReport(available=True, health="PASSED",
                                       percent_used=2, available_spare=95,
                                       spare_threshold=10, media_errors=0)
        codes = self._codes(rep)
        self.assertNotIn("smart.spare_low", codes)  # 95 > 10: normal aging
        rep.smart = models.SmartReport(available=True, health="PASSED",
                                       percent_used=80, available_spare=8,
                                       spare_threshold=10, media_errors=0)
        self.assertIn("smart.spare_low", self._codes(rep))

    def test_critical_warning_bitmask(self):
        rep = _base_report()
        rep.smart = models.SmartReport(available=True, health="PASSED",
                                       critical_warning=2)
        self.assertIn("smart.critical_warning", self._codes(rep))

    def test_throttle_and_writerate(self):
        rep = _base_report()
        rep.system = models.SystemReport(available=True, cpu_speed_limit=62)
        self.assertIn("thermal.throttling", self._codes(rep))
        rep = _base_report()
        rep.writerate = models.WriteRateReport(available=True, mb_per_s=450.0)
        self.assertIn("writerate.storm", self._codes(rep))

    def test_crashes_frequent(self):
        rep = _base_report()
        rep.crashes = models.CrashReport(available=True,
                                         weekly={"Cursor": 5}, total_weekly=5)
        self.assertIn("crashes.frequent", self._codes(rep))

    def test_external_unhealthy(self):
        rep = _base_report()
        rep.external_smart = [models.SmartReport(available=True,
                                                 health="FAILED!")]
        self.assertIn("smart.external_unhealthy", self._codes(rep))

    def test_domain_statuses(self):
        rep = _base_report()
        rep.backup = models.BackupReport(available=True, configured=False)
        findings = analyze.analyze(rep, [], dict(DEFAULTS))
        dom = analyze.domain_statuses(findings, rep)
        self.assertEqual(dom["backup"], "critical")
        self.assertEqual(set(dom), set(analyze.DOMAINS))
        # drive collector unavailable in _base_report → unknown (no findings)
        self.assertEqual(dom["drive"], "unknown")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_analyze -v` → all pass (existing 10 + new 10, minus any sanctioned spare-rule edit)
- [ ] **Step 4: Commit** — `git add ssdwtf/analyze.py tests/test_analyze.py && git commit -m "phase1: domain dashboard + backup/pressure/apfs/thrash findings"`

---

### Task 11: cli.py tiers + metrics + report.py domains

**Files:**
- Modify: `ssdwtf/cli.py` (build_report tiers, `--fast`, metrics.record)
- Modify: `ssdwtf/report.py` (domain table, JSON domains + evidence)
- Test: `tests/test_cli.py`, `tests/test_report.py` (extend only; existing assertions must keep passing — `test_report.py` may be extended for the new JSON keys per Global Constraints)

**Interfaces:**
- Consumes: everything from Tasks 1–10.
- Produces: `build_report(config, fast=False)`; `scan --fast`, `watch --fast`; JSON payload keys `domains` and per-finding `evidence`; `report.domain_table(domains) -> list[str]`.

- [ ] **Step 1: Rewire `ssdwtf/cli.py`**

Add imports:

```python
from . import metrics
from .collectors import apfs as apfs_col
from .collectors import backup as backup_col
from .collectors import crashes as crashes_col
from .collectors import pressure as pressure_col
from .collectors import smartext as smartext_col
from .collectors import system as system_col
from .collectors import writerate as writerate_col
from .models import ApfsReport, BackupReport, CrashReport, StateDirReport
```

Replace `build_report` and `_run_scan` with:

```python
def build_report(config: dict, fast: bool = False) -> HealthReport:
    slow = set(config.get("tiers", {}).get("slow", []))

    def want(name: str) -> bool:
        return not (fast and name in slow)

    crashes_cfg = config.get("crashes", {})
    return HealthReport(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        host_ram_gb=host_ram_gb(),
        smart=smart_col.collect_smart(config["smart"]["device"]),
        swap=swap_col.collect_swap(),
        disk=disk_col.collect_disk(config["disk"]["mount"]),
        processes=proc_col.collect_processes(config["procs"]["ghost_days"]),
        statedirs=(statedirs_col.collect_statedirs() if want("statedirs")
                   else StateDirReport(note="not collected (--fast)")),
        pressure=pressure_col.collect_pressure(),
        system=system_col.collect_system(),
        apfs=(apfs_col.collect_apfs(config["disk"]["mount"]) if want("apfs")
              else ApfsReport(available=False, error="not collected (--fast)")),
        backup=(backup_col.collect_backup()
                if want("backup") and config.get("backup", {}).get("enabled", True)
                else BackupReport(available=False, error="not collected (--fast)")),
        crashes=(crashes_col.collect_crashes(crashes_cfg.get("apps", []))
                 if want("crashes")
                 else CrashReport(available=False, error="not collected (--fast)")),
        writerate=writerate_col.collect_writerate(
            config.get("writerate", {}).get("device", "disk0")),
        external_smart=[smartext_col.collect_smart_external(d)
                        for d in config["smart"].get("external_devices", [])],
    )


def _run_scan(config: dict, use_history: bool,
              fast: bool = False) -> tuple[HealthReport, list, int]:
    rep = build_report(config, fast=fast)
    if use_history:
        history.append_history(rep)
        metrics.record(rep)
    hist = history.load_history()
    findings = analyze.analyze(rep, hist, config)
    return rep, findings, _exit_code(findings)
```

Thread `fast` through: `cmd_scan` calls `_run_scan(config, use_history=not args.no_history, fast=args.fast)`;
`cmd_watch` passes `fast=args.fast` in both the `--once` and loop paths.
Add to the `scan` parser: `p.add_argument("--fast", action="store_true", help="fast tier only (skip slow collectors)")`
and the same line to the `watch` parser.

- [ ] **Step 2: Extend `ssdwtf/report.py`**

Add the domain table renderer and wire it into `render_text` (insert the
table right after the `_bar` line) and `render_json`:

```python
def domain_table(domains: dict[str, str]) -> list[str]:
    lines = ["== DOMAINS =="]
    for name, status in domains.items():
        marker = {"ok": "ok", "warn": "WARN", "critical": "CRIT",
                  "unknown": " ? "}.get(status, status)
        lines.append(f"  [{marker:>4}] {name}")
    return lines
```

In `render_text`, after `lines: list[str] = [_bar(report), ""]` insert:

```python
    lines.extend(domain_table(analyze_domain_statuses(findings, report)))
    lines.append("")
```

with a new import at top: `from .analyze import domain_statuses as analyze_domain_statuses, grade, health_score`
(replacing the existing analyze import line).

In `render_json`, add `"evidence": f.evidence` to each findings dict and
`"domains": analyze_domain_statuses(findings, report)` to the payload.

- [ ] **Step 3: Extend tests**

`tests/test_report.py`: run first. If `render_json` assertions fail on the
new keys, extend the expected payload to include `domains` and `evidence`
(add, never remove assertions). Add a new test:

```python
class TestDomainTable(unittest.TestCase):
    def test_domain_table_marks_statuses(self):
        lines = report.domain_table({"drive": "ok", "backup": "critical"})
        joined = "\n".join(lines)
        self.assertIn("CRIT", joined)
        self.assertIn("backup", joined)
```

`tests/test_cli.py`: add a fast-mode test following the file's existing
mocking pattern (patch `build_report` and check `fast=True` propagates, or
patch the slow collectors and assert they are not called under `--fast`):

```python
    def test_scan_fast_skips_slow_collectors(self):
        with mock.patch.object(cli.statedirs_col, "collect_statedirs") as m_sd, \
             mock.patch.object(cli.apfs_col, "collect_apfs") as m_ap, \
             mock.patch.object(cli.backup_col, "collect_backup") as m_bu, \
             mock.patch.object(cli.crashes_col, "collect_crashes") as m_cr, \
             mock.patch.object(cli.smart_col, "collect_smart") as m_sm, \
             mock.patch.object(cli.swap_col, "collect_swap", return_value=None), \
             mock.patch.object(cli.disk_col, "collect_disk", return_value=None), \
             mock.patch.object(cli.proc_col, "collect_processes") as m_pr, \
             mock.patch.object(cli.pressure_col, "collect_pressure") as m_prs, \
             mock.patch.object(cli.system_col, "collect_system") as m_sys, \
             mock.patch.object(cli.writerate_col, "collect_writerate") as m_wr, \
             mock.patch.object(cli.history, "append_history"), \
             mock.patch.object(cli.history, "load_history", return_value=[]), \
             mock.patch.object(cli.metrics, "record"):
            m_sm.return_value = models.SmartReport(available=False, error="x")
            m_pr.return_value = models.ProcessReport()
            m_prs.return_value = models.PressureReport(available=False)
            m_sys.return_value = models.SystemReport(available=False)
            m_wr.return_value = models.WriteRateReport(available=False)
            code = cli.main(["scan", "--fast", "--json"])
            self.assertIn(code, (0, 1, 2))
            m_sd.assert_not_called()
            m_ap.assert_not_called()
            m_bu.assert_not_called()
            m_cr.assert_not_called()
```

(Adjust to match the file's actual import/mock style — `models` may need
importing there; follow how the existing cli tests build fake reports.)

- [ ] **Step 4: Run tests** — `python3 -m unittest tests.test_cli tests.test_report -v` → all pass
- [ ] **Step 5: Commit** — `git add ssdwtf/cli.py ssdwtf/report.py tests/test_cli.py tests/test_report.py && git commit -m "phase1: --fast tier, metrics recording, domain table in reports"`

---

### Task 12: Docs sync + full verification

**Files:**
- Modify: `README.md`, `AGENTS.md`, `docs/superpowers/specs/2026-07-30-ssdwtf-design.md` (patch the two lines the expansion supersedes)

**Interfaces:** none (docs + verification).

- [ ] **Step 1: Patch the base spec** (`2026-07-30-ssdwtf-design.md`)
  - In §4.1's table, change the SSD-wear threshold cell: replace "critical if available_spare < 100" with "critical if NVMe Critical Warning ≠ 0, or available_spare below the device-reported threshold (see the monitor-expansion spec)".
  - In §5 CLI surface, note `scan`/`watch` accept `--fast` (fast tier only).
  - No other edits — the expansion spec carries the rest.

- [ ] **Step 2: Update README.md** — add to the appropriate existing sections (match the file's current structure and tone; do not restructure):
  - `scan --fast` / `watch --fast` one-liner.
  - New "Domains" description: the eight domain statuses shown above findings.
  - New monitored signals: memory pressure, uptime/throttle/battery, APFS local snapshots, Time Machine readiness, crash frequency, write rate, external drives (`smart.external_devices` config), NVMe critical warning.
  - New config keys summary (tiers, backup, apfs, pressure, crashes, thermal, uptime, writerate, battery, smart.external_devices).

- [ ] **Step 3: Update AGENTS.md**
  - Code-organization block: add `metrics.py` and the seven new collector files with one-line roles.
  - Testing section: update the expected test count to the new total (compute it from the verification run below).
  - Config section: add the new keys.
  - Data-flow note: every scan/watch appends history AND records metrics to `~/.local/share/ssdwtf/metrics.db`.

- [ ] **Step 4: Full verification (from repo root)**

```sh
python3 -m unittest discover -s tests 2>&1 | tail -3   # ALL tests OK — record the count
python3 -m ssdwtf scan --json | python3 -m json.tool > /dev/null && echo "json ok"
python3 -m ssdwtf scan --fast; echo "fast exit: $?"     # completes visibly faster, domain table present
python3 -m ssdwtf scan; echo "exit: $?"                 # full scan, domain table present
python3 -m ssdwtf history | tail -3                     # still works on old+new rows
ls -la ~/.local/share/ssdwtf/metrics.db                 # metrics store created
```

Every command must behave: valid JSON, exit codes in {0,1,2}, no tracebacks,
domain table shows real statuses (backup will be `critical`/`warn` on the
dev machine — its destination is configured but unmounted; that is correct,
honest monitoring, not a bug).

- [ ] **Step 5: Commit** — `git add README.md AGENTS.md docs/superpowers/specs/2026-07-30-ssdwtf-design.md && git commit -m "phase1: docs sync (README, AGENTS, base spec patches)"`

---

## Self-Review Notes (already applied)

- `pressure.sustained_min` exists in config but sustained-pressure logic is
  deferred to Phase 3 (needs the metrics store to have accumulated real
  samples); Phase 1 fires on the current level only. Spec §4 table updated
  to match.
- Purgeable space is not exposed by `diskutil info` on macOS 26 — dropped as
  a metric, kept `container_free_gb`; spec updated to match.
- `test_report.py` extension (not just addition) is the one sanctioned
  existing-test edit besides the `smart.spare_low` rule change in Task 10.
