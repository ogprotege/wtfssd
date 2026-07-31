from __future__ import annotations

from typing import Callable, Optional

from ..models import WriteRateReport
from ._run import run_cmd


def parse_iostat(text: str) -> Optional[float]:
    """iostat -d -w 1 -c 2 <dev> → MB/s from the LAST sample row.
    Rows are: KB/t tps MB/s (three floats). The first row is the
    since-boot average; the last is the current interval rate."""
    rows: list[list[str]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3:
            try:
                [float(p) for p in parts]
            except ValueError:
                continue
            rows.append(parts)
    if not rows:
        return None
    return float(rows[-1][2])


def collect_writerate(device: str,
                      runner: Callable = run_cmd) -> WriteRateReport:
    out = runner(["iostat", "-d", "-w", "1", "-c", "2", device])
    if out is None:
        return WriteRateReport(available=False, error="iostat unavailable")
    rate = parse_iostat(out)
    if rate is None:
        return WriteRateReport(available=False,
                               error=f"unparseable iostat output for {device}")
    return WriteRateReport(available=True, mb_per_s=rate)
