from __future__ import annotations

import re
import time
from typing import Callable, Optional

from ..models import SystemReport
from ._run import run_cmd

_BOOT_RE = re.compile(r"sec\s*=\s*(\d+)")
_LIMIT_RE = re.compile(r"CPU_Speed_Limit\s*=\s*(\d+)")
# top-level ioreg keys have spaces around '='; nested BatteryData does not
_CYCLE_RE = re.compile(r'"CycleCount"\s+=\s+(\d+)')
_CAP_RE = re.compile(r'"MaxCapacity"\s+=\s+(\d+)')


def parse_boot_time(text: str) -> Optional[int]:
    m = _BOOT_RE.search(text)
    return int(m.group(1)) if m else None


def parse_cpu_speed_limit(text: str) -> int:
    """pmset -g therm → current CPU speed limit %. 100 = not throttled;
    the 'No ... recorded' notes mean no limit is in effect."""
    m = _LIMIT_RE.search(text)
    return int(m.group(1)) if m else 100


def parse_battery(text: str) -> tuple[Optional[int], Optional[int]]:
    cycle = _CYCLE_RE.search(text)
    cap = _CAP_RE.search(text)
    return (int(cycle.group(1)) if cycle else None,
            int(cap.group(1)) if cap else None)


def collect_system(runner: Callable = run_cmd,
                   now: Optional[float] = None) -> SystemReport:
    """Uptime (kern.boottime), thermal throttle state (pmset), battery (ioreg).
    Degrades per-source: a laptop-less Mac simply reports battery_present=False."""
    now = time.time() if now is None else now
    rep = SystemReport(available=True)

    out = runner(["sysctl", "kern.boottime"])
    boot = parse_boot_time(out) if out else None
    rep.uptime_days = round((now - boot) / 86400.0, 2) if boot else None

    therm = runner(["pmset", "-g", "therm"])
    rep.cpu_speed_limit = parse_cpu_speed_limit(therm) if therm else None

    bat = runner(["ioreg", "-rn", "AppleSmartBattery"])
    if bat:
        cycle, cap = parse_battery(bat)
        rep.battery_present = cycle is not None or cap is not None
        rep.battery_cycle_count = cycle
        rep.battery_max_capacity_pct = cap

    if rep.uptime_days is None and rep.cpu_speed_limit is None:
        return SystemReport(available=False, error="sysctl/pmset unavailable")
    return rep
