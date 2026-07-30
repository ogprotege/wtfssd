from __future__ import annotations

import re
from typing import Callable, Optional

from ..models import SwapReport
from ._run import run_cmd


def parse_swapusage(text: str) -> SwapReport:
    def grab(key: str) -> float:
        m = re.search(rf"{key} = ([\d.]+)M", text)
        return float(m.group(1)) if m else 0.0
    return SwapReport(
        total_mb=grab("total"), used_mb=grab("used"), free_mb=grab("free"),
        encrypted="(encrypted)" in text,
    )


def collect_swap(runner: Callable = run_cmd) -> Optional[SwapReport]:
    text = runner(["sysctl", "vm.swapusage"])
    if text is None:
        return None
    return parse_swapusage(text)
