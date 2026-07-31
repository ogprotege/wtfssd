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
