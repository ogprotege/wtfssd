from __future__ import annotations

from typing import Callable, Optional

from ..models import DiskReport
from ._run import run_cmd

KB_TO_GB = 1024 / 1e9  # 1K-blocks → decimal GB


def parse_df(text: str, mount: str) -> DiskReport:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        raise ValueError("empty df output")
    parts = lines[-1].split()
    # Capacity is the first N% token (before iused / %iused). Working from
    # that index keeps "Mounted on" joinable when the mount path has spaces.
    cap_idx = None
    for i, tok in enumerate(parts):
        if tok.endswith("%") and tok[:-1].replace(".", "", 1).isdigit():
            cap_idx = i
            break
    if cap_idx is None or cap_idx < 3:
        raise ValueError("no capacity column in df output")
    total_kb = int(parts[cap_idx - 3])
    used_kb = int(parts[cap_idx - 2])
    avail_kb = int(parts[cap_idx - 1])
    pct_used = float(parts[cap_idx].rstrip("%"))
    mount_parts = parts[cap_idx + 4:] if len(parts) > cap_idx + 4 else []
    found = " ".join(mount_parts) if mount_parts else mount
    return DiskReport(
        mount=found if (found == mount or mount in found) else mount,
        size_gb=total_kb * KB_TO_GB,
        used_gb=used_kb * KB_TO_GB,
        avail_gb=avail_kb * KB_TO_GB,
        pct_used=pct_used,
        pct_free=100.0 - pct_used,
    )


def collect_disk(mount: str = "/System/Volumes/Data",
                 runner: Callable = run_cmd) -> Optional[DiskReport]:
    text = runner(["df", "-k", mount])
    if text is None:
        return None
    try:
        return parse_df(text, mount)
    except (ValueError, IndexError, TypeError):
        return None
