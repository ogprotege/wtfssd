from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class SmartReport:
    available: bool
    error: Optional[str] = None
    model: str = ""
    health: str = ""                      # e.g. "PASSED"
    percent_used: Optional[int] = None
    available_spare: Optional[int] = None  # percent
    media_errors: Optional[int] = None
    power_on_hours: Optional[int] = None
    data_units_written: Optional[int] = None  # NVMe units of 512,000 bytes
    tb_written: Optional[float] = None


@dataclass
class SwapReport:
    total_mb: float
    used_mb: float
    free_mb: float
    encrypted: bool = False


@dataclass
class DiskReport:
    mount: str
    size_gb: float
    used_gb: float
    avail_gb: float
    pct_used: float  # 0-100
    pct_free: float  # 0-100


@dataclass
class GhostProcess:
    pid: int
    ppid: int
    name: str
    age_seconds: int
    rss_mb: float


@dataclass
class ProcessReport:
    ghosts: list[GhostProcess] = field(default_factory=list)
    total_ide_processes: int = 0
    note: Optional[str] = None


@dataclass
class StateDir:
    key: str
    path: str
    exists: bool
    size_bytes: int
    note: str = ""


@dataclass
class StateDirReport:
    dirs: list[StateDir] = field(default_factory=list)
    total_bytes: int = 0
    note: Optional[str] = None


@dataclass
class Finding:
    pillar: str    # "monitor" | "clean" | "optimize"
    severity: str  # "info" | "warn" | "critical"
    code: str      # stable id, e.g. "swap.high" — used for alert cooldown
    title: str
    detail: str
    recommendation: str


@dataclass
class HealthReport:
    timestamp: str  # ISO 8601 local, e.g. "2026-07-30T10:53:07"
    host_ram_gb: float
    smart: SmartReport
    swap: Optional[SwapReport]
    disk: Optional[DiskReport]
    processes: ProcessReport
    statedirs: StateDirReport


def report_to_dict(report: HealthReport) -> dict[str, Any]:
    return asdict(report)


def report_from_dict(d: dict[str, Any]) -> HealthReport:
    smart = SmartReport(**d["smart"])
    swap = SwapReport(**d["swap"]) if d.get("swap") else None
    disk = DiskReport(**d["disk"]) if d.get("disk") else None
    procs = ProcessReport(
        ghosts=[GhostProcess(**g) for g in d["processes"].get("ghosts", [])],
        total_ide_processes=d["processes"].get("total_ide_processes", 0),
        note=d["processes"].get("note"),
    )
    statedirs = StateDirReport(
        dirs=[StateDir(**s) for s in d["statedirs"].get("dirs", [])],
        total_bytes=d["statedirs"].get("total_bytes", 0),
        note=d["statedirs"].get("note"),
    )
    return HealthReport(
        timestamp=d["timestamp"],
        host_ram_gb=d["host_ram_gb"],
        smart=smart,
        swap=swap,
        disk=disk,
        processes=procs,
        statedirs=statedirs,
    )


def make_empty_report(timestamp: str, host_ram_gb: float) -> HealthReport:
    """Baseline report with every subsystem marked unavailable/empty."""
    return HealthReport(
        timestamp=timestamp,
        host_ram_gb=host_ram_gb,
        smart=SmartReport(available=False, error="not collected"),
        swap=None,
        disk=None,
        processes=ProcessReport(note="not collected"),
        statedirs=StateDirReport(note="not collected"),
    )
