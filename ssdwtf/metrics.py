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
        # error set → tmutil failed and snapshot_count is the unmeasured
        # default; never record a zero for data we did not measure. The
        # container-free source (diskutil) is independent and succeeded.
        if apfs.error is None:
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
