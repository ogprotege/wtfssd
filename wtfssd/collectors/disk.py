from __future__ import annotations

from typing import Callable, Optional

from ..models import DiskReport
from ._run import run_cmd

KB_TO_GB = 1024 / 1e9  # 1K-blocks → decimal GB


def parse_df(text: str, mount: str) -> DiskReport:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    parts = lines[-1].split()
    total_kb = int(parts[-8])
    used_kb = int(parts[-7])
    avail_kb = int(parts[-6])
    pct_used = float(parts[-5].rstrip("%"))
    return DiskReport(
        mount=parts[-1] if parts[-1] == mount else mount,
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
    return parse_df(text, mount)
