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
