from __future__ import annotations

from typing import Callable, Optional

from ..models import SpotlightReport
from ._run import run_cmd

_MDS_NAMES = ("mds_stores", "mdworker")


def parse_mdutil(text: str) -> Optional[bool]:
    if "Indexing enabled" in text:
        return True
    if "Indexing disabled" in text:
        return False
    return None


def parse_mds_cpu(ps_text: str) -> float:
    """Sum %CPU of mds_stores/mdworker from `ps -eo pcpu,comm`."""
    total = 0.0
    for line in ps_text.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            cpu = float(parts[0])
        except ValueError:
            continue
        if any(name in parts[1] for name in _MDS_NAMES):
            total += cpu
    return total


def collect_spotlight(runner: Callable = run_cmd) -> SpotlightReport:
    md = runner(["mdutil", "-s", "/"])
    ps = runner(["ps", "-eo", "pcpu,comm"])
    if md is None and ps is None:
        return SpotlightReport(available=False, error="mdutil/ps unavailable")
    rep = SpotlightReport(available=True)
    if md is not None:
        rep.indexing_enabled = parse_mdutil(md)
    if ps is not None:
        rep.mds_cpu_pct = parse_mds_cpu(ps)
    return rep
