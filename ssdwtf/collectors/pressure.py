from __future__ import annotations

import re
from typing import Callable, Optional

from ..models import PressureReport
from ._run import run_cmd

_LEVEL_RE = re.compile(r"^\s*(\d+)\s*$")
_FREE_RE = re.compile(r"System-wide memory free percentage:\s*(\d+)%")


def parse_pressure_level(text: str) -> Optional[int]:
    m = _LEVEL_RE.match(text)
    return int(m.group(1)) if m else None


def parse_memory_pressure_free(text: str) -> Optional[float]:
    m = _FREE_RE.search(text)
    return float(m.group(1)) if m else None


def collect_pressure(runner: Callable = run_cmd) -> PressureReport:
    """Memory pressure: sysctl level primary, memory_pressure free-% as context."""
    out = runner(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"])
    if out is None:
        return PressureReport(available=False, error="sysctl unavailable")
    level = parse_pressure_level(out)
    if level is None:
        return PressureReport(available=False,
                              error=f"unparseable pressure level: {out.strip()[:40]}")
    free_pct = None
    mp = runner(["memory_pressure"])
    if mp is not None:
        free_pct = parse_memory_pressure_free(mp)
    return PressureReport(available=True, level=level, free_pct=free_pct)
