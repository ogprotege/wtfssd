from __future__ import annotations

import re
from typing import Callable, Optional

from ..models import SwapReport
from ._run import run_cmd


_TO_MB = {"K": 1 / 1024, "M": 1.0, "G": 1024.0}


def parse_swapusage(text: str) -> SwapReport:
    def grab(key: str) -> float:
        m = re.search(rf"{key} = ([\d.]+)([KMG])", text)
        if not m:
            raise ValueError(f"missing {key} in swapusage")
        return float(m.group(1)) * _TO_MB[m.group(2)]
    return SwapReport(
        total_mb=grab("total"), used_mb=grab("used"), free_mb=grab("free"),
        encrypted="(encrypted)" in text,
    )


def collect_swap(runner: Callable = run_cmd) -> Optional[SwapReport]:
    text = runner(["sysctl", "vm.swapusage"])
    if text is None:
        return None
    try:
        return parse_swapusage(text)
    except (ValueError, KeyError, TypeError):
        return None
