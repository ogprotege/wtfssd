from __future__ import annotations

from typing import Callable, Optional

from ..models import FdsReport
from ._run import run_cmd
from .processes import IDE_PATTERNS


def parse_lsof(text: str) -> dict[int, tuple[str, int]]:
    """lsof -nP output → {pid: (command, open-fd count)}. Header skipped."""
    counts: dict[int, tuple[str, int]] = {}
    for line in text.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4 or not parts[1].isdigit():
            continue
        command, pid = parts[0], int(parts[1])
        name, n = counts.get(pid, (command, 0))
        counts[pid] = (name, n + 1)
    return counts


def _family(command: str) -> Optional[str]:
    low = command.lower()
    for pat in IDE_PATTERNS:
        if pat.strip("/. ") in low:
            return pat.strip("/. ")
    return None


def collect_fds(runner: Callable = run_cmd) -> FdsReport:
    """Open-fd counts per watched IDE family + the single worst pid.
    lsof is slow (~1-3 s) — this collector belongs to the slow tier."""
    out = runner(["lsof", "-nP"])
    if out is None:
        return FdsReport(available=False, error="lsof unavailable")
    per_pid = parse_lsof(out)
    per_app: dict[str, int] = {}
    max_pid, max_name, max_count = 0, "", 0
    for pid, (command, count) in per_pid.items():
        fam = _family(command)
        if fam is not None:
            per_app[fam] = per_app.get(fam, 0) + count
        if count > max_count:
            max_pid, max_name, max_count = pid, command, count
    return FdsReport(available=True, per_app=per_app,
                     max_pid=max_pid, max_name=max_name, max_count=max_count)
