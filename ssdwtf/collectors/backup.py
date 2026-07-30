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
