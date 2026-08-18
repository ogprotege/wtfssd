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
    ide_procs: list[GhostProcess] = field(default_factory=list)  # ALL IDE-family procs, any age


@dataclass
class StateDir:
    key: str
    path: str
    exists: bool
    size_bytes: int
    note: str = ""
    category: str = ""  # ai-state|ide-cache|build-artifacts|models|user-caches|dev-deps


@dataclass
class StateDirReport:
    dirs: list[StateDir] = field(default_factory=list)
    total_bytes: int = 0
    note: Optional[str] = None
    category_totals: dict[str, int] = field(default_factory=dict)


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
class WriterProc:
    """One process's cumulative disk writes (proc_pid_rusage, no root)."""
    pid: int
    name: str              # full command path from ps comm
    written_bytes: int     # cumulative since the process started
    elapsed_seconds: int   # process age, for rate context


@dataclass
class WritersReport:
    """Per-process write attribution. Only LIVE processes are visible —
    exited processes take their counters with them, so visible_total_bytes
    is a floor, not the machine's total."""
    available: bool
    error: Optional[str] = None
    top: list[WriterProc] = field(default_factory=list)
    visible_total_bytes: int = 0
    process_count: int = 0
    note: Optional[str] = None


@dataclass
class ChurnReport:
    available: bool
    error: Optional[str] = None
    pack_count: int = 0
    pack_bytes: int = 0
    added: int = 0
    removed: int = 0
    added_bytes: int = 0
    note: Optional[str] = None  # "baseline stored" on first run


@dataclass
class FdsReport:
    available: bool
    error: Optional[str] = None
    per_app: dict[str, int] = field(default_factory=dict)
    max_pid: int = 0
    max_name: str = ""
    max_count: int = 0


@dataclass
class MCPServer:
    name: str
    command: str
    live_pids: int = 0
    rss_mb: float = 0.0
    oldest_age_s: int = 0


@dataclass
class MCPReport:
    available: bool
    error: Optional[str] = None
    claude_running: bool = False
    servers: list[MCPServer] = field(default_factory=list)


@dataclass
class SecretMatch:
    path: str
    line: int
    rule: str


@dataclass
class SecretsReport:
    available: bool
    error: Optional[str] = None
    enabled: bool = False
    scanned_files: int = 0
    matches: list[SecretMatch] = field(default_factory=list)


@dataclass
class RetentionEntry:
    tool: str
    setting: str
    status: str                   # "configured" | "absent"
    value: Optional[int] = None


@dataclass
class RetentionReport:
    available: bool
    error: Optional[str] = None
    tools: list[RetentionEntry] = field(default_factory=list)


@dataclass
class LaunchdReport:
    available: bool
    error: Optional[str] = None
    agent_count: int = 0
    new_since_baseline: list[str] = field(default_factory=list)
    baseline_exists: bool = True


@dataclass
class SpotlightReport:
    available: bool
    error: Optional[str] = None
    indexing_enabled: Optional[bool] = None
    mds_cpu_pct: Optional[float] = None


@dataclass
class LogsReport:
    available: bool
    error: Optional[str] = None
    total_bytes: int = 0
    top: list[StateDir] = field(default_factory=list)


@dataclass
class RepoStatus:
    path: str
    error: Optional[str] = None
    uncommitted: int = 0
    untracked: int = 0
    has_remote: bool = True
    unpushed: int = 0


@dataclass
class GitWatchReport:
    available: bool
    error: Optional[str] = None
    repos: list[RepoStatus] = field(default_factory=list)


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
    churn: ChurnReport = field(default_factory=lambda: ChurnReport(available=False))
    fds: FdsReport = field(default_factory=lambda: FdsReport(available=False))
    mcp: MCPReport = field(default_factory=lambda: MCPReport(available=False))
    secrets: SecretsReport = field(default_factory=lambda: SecretsReport(available=False))
    retention: RetentionReport = field(default_factory=lambda: RetentionReport(available=False))
    launchd: LaunchdReport = field(default_factory=lambda: LaunchdReport(available=False))
    spotlight: SpotlightReport = field(default_factory=lambda: SpotlightReport(available=False))
    logs: LogsReport = field(default_factory=lambda: LogsReport(available=False))
    gitwatch: GitWatchReport = field(default_factory=lambda: GitWatchReport(available=False))
    writers: WritersReport = field(default_factory=lambda: WritersReport(available=False))
    # Recorded so history can tell full vs fast/micro and bulk vs AI-core.
    # None = legacy history row (infer at display time from statedirs/smart).
    scan_tier: Optional[str] = None   # "micro" | "fast" | "full" | None
    bulk_state: bool = False          # True when bulk statedirs were included


def report_to_dict(report: HealthReport) -> dict[str, Any]:
    return asdict(report)


def report_from_dict(d: dict[str, Any]) -> HealthReport:
    smart = SmartReport(**{k: v for k, v in d["smart"].items()
                           if k in SmartReport.__dataclass_fields__})
    swap = SwapReport(**d["swap"]) if d.get("swap") else None
    disk = DiskReport(**d["disk"]) if d.get("disk") else None
    def _ghosts(raw_list: Any) -> list[GhostProcess]:
        if not isinstance(raw_list, list):
            return []
        out: list[GhostProcess] = []
        for g in raw_list:
            if not isinstance(g, dict):
                continue
            try:
                out.append(GhostProcess(**{k: v for k, v in g.items()
                                           if k in GhostProcess.__dataclass_fields__}))
            except TypeError:
                continue
        return out

    procs = ProcessReport(
        ghosts=_ghosts(d["processes"].get("ghosts", [])),
        total_ide_processes=d["processes"].get("total_ide_processes", 0),
        note=d["processes"].get("note"),
        ide_procs=_ghosts(d["processes"].get("ide_procs", [])),
    )
    statedirs = StateDirReport(
        dirs=[StateDir(**{k: v for k, v in s.items()
                          if k in StateDir.__dataclass_fields__})
              for s in d["statedirs"].get("dirs", [])],
        total_bytes=d["statedirs"].get("total_bytes", 0),
        note=d["statedirs"].get("note"),
        category_totals=d["statedirs"].get("category_totals", {}),
    )

    def _sub(cls, key):
        raw = d.get(key)
        if not raw:
            return cls(available=False)
        return cls(**{k: v for k, v in raw.items()
                      if k in cls.__dataclass_fields__})

    def _sublist(cls, item_cls, key, list_field):
        raw = d.get(key)
        if not raw:
            return cls(available=False)
        kwargs = {k: v for k, v in raw.items()
                  if k in cls.__dataclass_fields__ and k != list_field}
        kwargs[list_field] = [item_cls(**{k: v for k, v in item.items()
                                          if k in item_cls.__dataclass_fields__})
                              for item in raw.get(list_field, [])]
        return cls(**kwargs)

    external = [SmartReport(**{k: v for k, v in s.items()
                               if k in SmartReport.__dataclass_fields__})
                for s in d.get("external_smart", [])]
    raw_tier = d.get("scan_tier")
    tier: Optional[str]
    if raw_tier in ("micro", "fast", "full"):
        tier = raw_tier
    else:
        tier = None  # legacy row — display layer infers
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
        churn=_sub(ChurnReport, "churn"),
        fds=_sub(FdsReport, "fds"),
        mcp=_sublist(MCPReport, MCPServer, "mcp", "servers"),
        secrets=_sublist(SecretsReport, SecretMatch, "secrets", "matches"),
        retention=_sublist(RetentionReport, RetentionEntry, "retention", "tools"),
        launchd=_sub(LaunchdReport, "launchd"),
        spotlight=_sub(SpotlightReport, "spotlight"),
        logs=_sublist(LogsReport, StateDir, "logs", "top"),
        gitwatch=_sublist(GitWatchReport, RepoStatus, "gitwatch", "repos"),
        writers=_sublist(WritersReport, WriterProc, "writers", "top"),
        scan_tier=tier,
        bulk_state=bool(d.get("bulk_state", False)),
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
