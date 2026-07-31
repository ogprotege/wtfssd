from __future__ import annotations

from typing import Callable

from ..models import SmartReport
from ._run import run_cmd
from .smart import parse_smartctl

_BRIDGES = ("auto", "sat")  # USB NVMe bridges usually need -d sat


def collect_smart_external(device: str,
                           runner: Callable = run_cmd) -> SmartReport:
    """SMART for an external drive, trying bridge protocols in order.
    available=False means: device absent, bridge unsupported, or smartctl
    missing — an unmounted/unplugged archive drive is data, not a crash."""
    for bridge in _BRIDGES:
        out = runner(["smartctl", "-a", "-d", bridge, device])
        if out is None:
            continue
        rep = parse_smartctl(out)
        if rep.model or rep.health:
            return rep
    return SmartReport(
        available=False,
        error=f"no SMART data from {device} (absent or unsupported bridge)")
