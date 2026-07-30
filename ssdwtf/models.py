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
    critical_warning: Optional[int] = None   # NVMe Critical Warning bitmask (0 = ok)
    spare_threshold: Optional[int] = None    # device-reported Available Spare Threshold %
    unsafe_shutdowns: Optional[int] = None
    temperature_c: Optional[int] = None      # composite temperature


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
class PressureReport:
    available: bool
    error: Optional[str] = None
    level: Optional[int] = None       # 1=normal, 2=warn, 4=critical (sysctl)
    free_pct: Optional[float] = None  # memory_pressure fallback


@dataclass
class SystemReport:
    available: bool
    error: Optional[str] = None
    uptime_days: Optional[float] = None
    cpu_speed_limit: Optional[int] = None  # 100 = not throttled
    battery_present: bool = False
    battery_cycle_count: Optional[int] = None
    battery_max_capacity_pct: Optional[int] = None


@dataclass
class ApfsReport:
    available: bool
    error: Optional[str] = None
    snapshot_count: int = 0
    oldest_snapshot_days: Optional[float] = None
    container_free_gb: Optional[float] = None
    volume_used_gb: Optional[float] = None


@dataclass
class BackupReport:
    available: bool
    error: Optional[str] = None
    configured: bool = False
    destination_present: bool = False
    last_backup_age_hours: Optional[float] = None
    destinations: list[str] = field(default_factory=list)


@dataclass
class CrashReport:
    available: bool
    error: Optional[str] = None
    weekly: dict[str, int] = field(default_factory=dict)
    total_weekly: int = 0


@dataclass
class WriteRateReport:
    available: bool
    error: Optional[str] = None
    mb_per_s: Optional[float] = None


@dataclass
class Finding:
    pillar: str    # "monitor" | "clean" | "optimize"
    severity: str  # "info" | "warn" | "critical"
    code: str      # stable id, e.g. "swap.high" — used for alert cooldown
    title: str
    detail: str
    recommendation: str
    evidence: str = "measured"  # measured|derived|correlated|inferred|reported|unavailable


@dataclass
class HealthReport:
    timestamp: str  # ISO 8601 local, e.g. "2026-07-30T10:53:07"
    host_ram_gb: float
    smart: SmartReport
    swap: Optional[SwapReport]
    disk: Optional[DiskReport]
    processes: ProcessReport
    statedirs: StateDirReport
    pressure: PressureReport = field(default_factory=lambda: PressureReport(available=False))
    system: SystemReport = field(default_factory=lambda: SystemReport(available=False))
    apfs: ApfsReport = field(default_factory=lambda: ApfsReport(available=False))
    backup: BackupReport = field(default_factory=lambda: BackupReport(available=False))
    crashes: CrashReport = field(default_factory=lambda: CrashReport(available=False))
    writerate: WriteRateReport = field(default_factory=lambda: WriteRateReport(available=False))
    external_smart: list[SmartReport] = field(default_factory=list)


def report_to_dict(report: HealthReport) -> dict[str, Any]:
    return asdict(report)


def report_from_dict(d: dict[str, Any]) -> HealthReport:
    smart = SmartReport(**{k: v for k, v in d["smart"].items()
                           if k in SmartReport.__dataclass_fields__})
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

    def _sub(cls, key, default_available=False):
        raw = d.get(key)
        if not raw:
            return cls(available=default_available)
        return cls(**{k: v for k, v in raw.items()
                      if k in cls.__dataclass_fields__})

    external = [SmartReport(**{k: v for k, v in s.items()
                               if k in SmartReport.__dataclass_fields__})
                for s in d.get("external_smart", [])]
    return HealthReport(
        timestamp=d["timestamp"],
        host_ram_gb=d["host_ram_gb"],
        smart=smart,
        swap=swap,
        disk=disk,
        processes=procs,
        statedirs=statedirs,
        pressure=_sub(PressureReport, "pressure"),
        system=_sub(SystemReport, "system"),
        apfs=_sub(ApfsReport, "apfs"),
        backup=_sub(BackupReport, "backup"),
        crashes=_sub(CrashReport, "crashes"),
        writerate=_sub(WriteRateReport, "writerate"),
        external_smart=external,
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
