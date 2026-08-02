from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .config import data_dir as default_data_dir
from .models import HealthReport, report_from_dict, report_to_dict


def history_path(data_dir: Path | None = None) -> Path:
    return (data_dir or default_data_dir()) / "history.jsonl"


def append_history(report: HealthReport, data_dir: Path | None = None) -> None:
    path = history_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(report_to_dict(report)) + "\n")


def load_history(limit: int | None = None,
                 data_dir: Path | None = None) -> list[HealthReport]:
    path = history_path(data_dir)
    if not path.exists():
        return []
    reports: list[HealthReport] = []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            reports.append(report_from_dict(json.loads(line)))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return reports[-limit:] if limit else reports


def _window_days(first: HealthReport, last: HealthReport) -> float | None:
    try:
        t0 = datetime.fromisoformat(first.timestamp)
        t1 = datetime.fromisoformat(last.timestamp)
    except ValueError:
        return None
    days = (t1 - t0).total_seconds() / 86400
    return days if days >= 1 / 24 else None  # require ≥ 1 hour window


def gb_written_per_day(history: list[HealthReport]) -> float | None:
    usable = [r for r in history
              if r.smart.available and r.smart.data_units_written is not None]
    if len(usable) < 2:
        return None
    days = _window_days(usable[0], usable[-1])
    if not days:
        return None
    delta = usable[-1].smart.data_units_written - usable[0].smart.data_units_written
    if delta < 0:
        return None  # counter reset
    return delta * 512_000 / 1e9 / days


def state_growth_gb_per_day(
    history: list[HealthReport],
    window_days: float = 14.0,
    *,
    min_samples: int = 4,
    min_span_days: float = 3.0,
    max_gb_day: float | None = 50.0,
) -> float | None:
    # skip rows where statedirs was not collected (e.g. scan --fast placeholders
    # with total_bytes=0) — a 0 at the window start would inflate the delta
    usable = [r for r in history if not r.statedirs.note]
    # cap the fit to the trailing window so a one-time step (e.g. new state
    # dirs added to the registry) stops inflating the rate after window_days
    cutoff = datetime.now() - timedelta(days=window_days)
    recent: list[HealthReport] = []
    for r in usable:
        try:
            ts = datetime.fromisoformat(r.timestamp)
        except ValueError:
            continue
        if ts >= cutoff:
            recent.append(r)
    if len(recent) < min_samples:
        return None
    days = _window_days(recent[0], recent[-1])
    if not days or days < min_span_days:
        return None
    delta = recent[-1].statedirs.total_bytes - recent[0].statedirs.total_bytes
    rate = delta / 1e9 / days
    # absurd rates are almost always baseline discontinuities (registry
    # expansion, first full statedirs after --fast-only history, etc.)
    if max_gb_day is not None and rate > max_gb_day:
        return None
    return rate
