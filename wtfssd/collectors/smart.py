from __future__ import annotations

import re
from typing import Callable, Optional

from ..models import SmartReport
from ._run import run_cmd


def _search_int(pattern: str, text: str) -> Optional[int]:
    m = re.search(pattern, text, re.MULTILINE)
    return int(m.group(1).replace(",", "")) if m else None


def _search_hex(pattern: str, text: str) -> Optional[int]:
    m = re.search(pattern, text, re.MULTILINE)
    return int(m.group(1), 16) if m else None


def parse_smartctl(text: str) -> SmartReport:
    rep = SmartReport(available=True)
    m = re.search(r"^Model Number:\s*(.+?)\s*$", text, re.MULTILINE)
    rep.model = m.group(1) if m else ""
    m = re.search(r"overall-health self-assessment test result:\s*(\w+)", text)
    rep.health = m.group(1) if m else ""
    rep.percent_used = _search_int(r"^Percentage Used:\s*(\d+)%", text)
    rep.available_spare = _search_int(r"^Available Spare:\s*(\d+)%", text)
    rep.media_errors = _search_int(r"Media and Data Integrity Errors:\s*([\d,]+)", text)
    rep.power_on_hours = _search_int(r"^Power On Hours:\s*([\d,]+)", text)
    rep.data_units_written = _search_int(r"Data Units Written:\s*([\d,]+)", text)
    m = re.search(r"Data Units Written:\s*[\d,]+\s*\[([\d.]+)\s*(TB|GB)\]", text)
    if m:
        value = float(m.group(1))
        rep.tb_written = value if m.group(2) == "TB" else value / 1000.0
    elif rep.data_units_written is not None:
        rep.tb_written = rep.data_units_written * 512_000 / 1e12
    rep.critical_warning = _search_hex(r"Critical Warning:\s*(0x[0-9A-Fa-f]+)", text)
    rep.spare_threshold = _search_int(r"Available Spare Threshold:\s*(\d+)%", text)
    rep.unsafe_shutdowns = _search_int(r"Unsafe Shutdowns:\s*([\d,]+)", text)
    rep.temperature_c = _search_int(r"^Temperature:\s*(\d+)\s*Celsius", text)
    return rep


def collect_smart(device: str = "/dev/disk0",
                  runner: Callable = run_cmd) -> SmartReport:
    text = runner(["smartctl", "-a", device])
    if text is None:
        return SmartReport(
            available=False,
            error=f"smartctl failed for {device} (not installed? brew install smartmontools)",
        )
    return parse_smartctl(text)
