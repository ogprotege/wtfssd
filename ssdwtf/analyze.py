from __future__ import annotations

from datetime import datetime

from .collectors.statedirs import vscdb_size_bytes
from .history import gb_written_per_day, state_growth_gb_per_day
from .models import Finding, HealthReport

GB = 1e9

DOMAINS: tuple[str, ...] = ("drive", "backup", "headroom", "memory",
                            "processes", "state", "stability", "telemetry")

_DOMAIN_BY_PREFIX = {
    "smart.": "drive",
    "backup.": "backup",
    "disk.": "headroom", "apfs.": "headroom",
    "swap.": "memory", "pressure.": "memory", "memory.": "memory",
    "procs.": "processes",
    "state.": "state",
    "crashes.": "stability", "thermal.": "stability", "uptime.": "stability",
    "writerate.": "telemetry", "battery.": "telemetry",
}


def _f(pillar: str, severity: str, code: str, title: str,
       detail: str, recommendation: str) -> Finding:
    return Finding(pillar=pillar, severity=severity, code=code,
                   title=title, detail=detail, recommendation=recommendation)


def analyze(report: HealthReport, history: list[HealthReport],
            config: dict) -> list[Finding]:
    findings: list[Finding] = []
    cfg_smart = config["smart"]
    cfg_swap = config["swap"]
    cfg_disk = config["disk"]
    cfg_procs = config["procs"]
    cfg_state = config["state"]

    # --- SMART / SSD wear ---
    smart = report.smart
    if not smart.available:
        findings.append(_f("monitor", "info", "smart.unavailable",
            "SMART data unavailable",
            smart.error or "smartctl not found",
            "Install smartmontools (brew install smartmontools) for ground-truth SSD wear data."))
    else:
        if smart.health and smart.health != "PASSED":
            findings.append(_f("monitor", "critical", "smart.health_failed",
                "Drive health self-assessment failed",
                f"SMART overall health: {smart.health}",
                "Back up now. Run `smartctl -a /dev/disk0` and investigate."))
        if (smart.media_errors or 0) > 0:
            findings.append(_f("monitor", "critical", "smart.media_errors",
                "Drive reports media/data errors",
                f"{smart.media_errors} media and data integrity errors",
                "Back up now and check `smartctl -a /dev/disk0` monthly."))
        # NVMe Critical Warning bitmask is the emergency channel (spec §4).
        if (smart.critical_warning or 0) != 0:
            findings.append(_f("monitor", "critical", "smart.critical_warning",
                f"Drive Critical Warning: 0x{smart.critical_warning:02x}",
                "The NVMe controller is reporting a reliability, temperature, or read-only condition.",
                "Back up now. Run `smartctl -a /dev/disk0` for the full log."))
        # Spare is only critical below the DEVICE'S OWN threshold — a drop
        # from 100% is normal aging, not an emergency (research §2).
        if (smart.available_spare is not None
                and smart.spare_threshold is not None
                and smart.available_spare < smart.spare_threshold):
            findings.append(_f("monitor", "critical", "smart.spare_low",
                f"Available spare {smart.available_spare}% below device threshold {smart.spare_threshold}%",
                "The controller is running out of replacement blocks.",
                "Back up now and monitor wear weekly."))
        tb = f"{smart.tb_written:.1f} TB written" if smart.tb_written is not None else "writes unknown"
        pct = f"{smart.percent_used}%" if smart.percent_used is not None else "?"
        hrs = f"{smart.power_on_hours} h" if smart.power_on_hours is not None else "?"
        findings.append(_f("monitor", "info", "smart.wear_info",
            f"SSD wear: {pct} of rated life used",
            f"{tb} over {hrs} power-on hours. The drive's own accounting is the only honest wear signal.",
            "Check monthly: `ssdwtf history`."))
        rate = gb_written_per_day(history)
        if rate is not None and rate >= cfg_smart["writes_warn_gb_day"]:
            findings.append(_f("monitor", "warn", "smart.write_rate",
                f"High write volume: ~{rate:.0f} GB/day",
                "Sustained writes at this rate are usually swap thrash or snapshot churn, not wear-out.",
                "Check swap (`ssdwtf scan`) and add ignore rules: `ssdwtf optimize ignore`."))

    # --- Swap ---
    if report.swap is not None:
        used_gb = report.swap.used_mb / 1024
        if used_gb >= cfg_swap["crit_gb"]:
            findings.append(_f("monitor", "critical", "swap.critical",
                f"Extreme swap usage: {used_gb:.1f} GB",
                "Every swapped GB is written and rewritten on the SSD. This is the #1 wear driver.",
                "Fully quit (Cmd+Q) agentic IDEs, or restart to drain swap."))
        elif used_gb >= cfg_swap["warn_gb"]:
            findings.append(_f("monitor", "warn", "swap.high",
                f"High swap usage: {used_gb:.1f} GB",
                "The machine is pretending it has more RAM than it does; overflow lives on the SSD.",
                "Quit long-running IDE windows you are not using."))

    # --- Disk headroom ---
    if report.disk is not None:
        free_pct = report.disk.pct_free
        if free_pct < cfg_disk["crit_free_pct"]:
            findings.append(_f("monitor", "critical", "disk.critical",
                f"Critically low free space: {free_pct:.0f}%",
                f"{report.disk.avail_gb:.0f} GB free of {report.disk.size_gb:.0f} GB. Below the floor where macOS and the SSD controller struggle.",
                "Run `ssdwtf clean` and aim for 15-25% free."))
        elif free_pct < cfg_disk["warn_free_pct"]:
            findings.append(_f("monitor", "warn", "disk.low",
                f"Low free space: {free_pct:.0f}%",
                f"{report.disk.avail_gb:.0f} GB free of {report.disk.size_gb:.0f} GB.",
                "Run `ssdwtf clean` to restore the 15-25% headroom floor."))

    # --- Ghost processes ---
    procs = report.processes
    if procs.ghosts:
        oldest = procs.ghosts[0]
        days = oldest.age_seconds / 86400
        findings.append(_f("monitor", "warn", "procs.ghosts",
            f"{len(procs.ghosts)} ghost IDE process(es), oldest alive {days:.0f} days",
            f"Oldest: {oldest.name} (pid {oldest.pid}, {oldest.rss_mb:.0f} MB RSS). Closed windows that never died.",
            "Cmd+Q the owning apps (red button is not enough), or `kill` the pids."))
    if procs.total_ide_processes > cfg_procs["warn_count"]:
        findings.append(_f("monitor", "warn", "procs.many",
            f"{procs.total_ide_processes} IDE-related processes running",
            "Agentic IDEs spawn helper trees that outlive their windows.",
            "Fully quit unused IDEs; check Activity Monitor."))

    # --- Agentic state ---
    sd = report.statedirs
    vscdb_gb = vscdb_size_bytes(sd) / GB
    if vscdb_gb >= cfg_state["vscdb_warn_gb"]:
        findings.append(_f("clean", "warn", "state.vscdb_large",
            f"Cursor chat database is {vscdb_gb:.1f} GB",
            "state.vscdb grows ~1 GB/day for heavy users, with no retention policy.",
            "Quit Cursor, then `ssdwtf clean cursor-vscdb-backups --apply` (and consider cursor-vscdb)."))
    total_gb = sd.total_bytes / GB
    if total_gb >= cfg_state["total_warn_gb"]:
        findings.append(_f("clean", "warn", "state.total_large",
            f"Agentic/tooling state totals {total_gb:.0f} GB",
            "Unbounded local state with no retention policy.",
            "Run `ssdwtf clean` to see safe reclaim targets."))
    growth = state_growth_gb_per_day(history)
    if growth is not None and growth >= cfg_state["growth_warn_gb_day"]:
        findings.append(_f("clean", "warn", "state.growth",
            f"State growing ~{growth:.1f} GB/day",
            "At this rate a small drive fills in weeks.",
            "Constrain the indexer: `ssdwtf optimize ignore` in each project root."))

    # --- Monthly SMART habit ---
    try:
        if datetime.fromisoformat(report.timestamp).day == 1:
            findings.append(_f("monitor", "info", "smart.monthly_check",
                "Monthly SSD check",
                "The habit that replaces doomscrolling: look at the drive's own accounting.",
                "`ssdwtf history` to see the wear trend."))
    except ValueError:
        pass

    # --- Backup readiness (its own domain: a green SSD never hides a red backup) ---
    bu = report.backup
    cfg_backup = config.get("backup", {})
    if bu.available and cfg_backup.get("enabled", True):
        if not bu.configured:
            findings.append(_f("monitor", "critical", "backup.none_configured",
                "No Time Machine destination configured",
                "The SSD is soldered to the logic board; local snapshots do not survive board failure.",
                "System Settings → Time Machine → add a destination."))
        else:
            if not bu.destination_present:
                findings.append(_f("monitor", "warn", "backup.destination_missing",
                    "Backup destination not mounted",
                    f"Configured: {', '.join(bu.destinations) or 'unknown'} — backups are not running.",
                    "Connect the backup drive."))
            age = bu.last_backup_age_hours
            if age is not None:
                if age >= cfg_backup.get("crit_hours", 168):
                    findings.append(_f("monitor", "critical", "backup.stale",
                        f"Last successful backup {age / 24:.0f} days ago",
                        "Restore readiness decays silently; this is the actual disaster domain.",
                        "Connect the backup drive and let a backup complete."))
                elif age >= cfg_backup.get("warn_hours", 48):
                    findings.append(_f("monitor", "warn", "backup.stale",
                        f"Last successful backup {age:.0f} h ago",
                        "Backups are falling behind.",
                        "Connect the backup drive."))

    # --- APFS local snapshots ---
    ap = report.apfs
    cfg_apfs = config.get("apfs", {})
    if ap.available and ap.oldest_snapshot_days is not None:
        days = cfg_apfs.get("snapshot_warn_days", 7)
        if ap.oldest_snapshot_days >= days:
            findings.append(_f("monitor", "warn", "apfs.snapshots_old",
                f"Local APFS snapshot {ap.oldest_snapshot_days:.0f} days old ({ap.snapshot_count} total)",
                "Local snapshots hold deleted blocks hostage — space you freed may not come back until they purge.",
                "`tmutil listlocalsnapshots /`; thin with `tmutil thinlocalsnapshots /` if space is tight."))

    # --- Memory pressure ---
    pr = report.pressure
    if pr.available and pr.level is not None:
        if pr.level >= 4:
            findings.append(_f("monitor", "critical", "pressure.critical",
                "Memory pressure CRITICAL",
                "The kernel is under extreme memory pressure; Apple Silicon masks it as silent thrashing.",
                "Quit memory-heavy apps; check ghost processes below."))
        elif pr.level >= 2:
            findings.append(_f("monitor", "warn", "pressure.warn",
                "Memory pressure elevated",
                f"Pressure level {pr.level} with {pr.free_pct:.0f}% free"
                if pr.free_pct is not None else f"Pressure level {pr.level}",
                "Watch for swap growth; consider closing unused IDE windows."))

    # --- Swap trend (derived from history) + thrash hint + restart hint ---
    swap_rate = _swap_rate_gb_day(history)
    if (swap_rate is not None and swap_rate > 0.5
            and pr.available and (pr.level or 1) >= 2):
        findings.append(_f("monitor", "warn", "memory.thrash_hint",
            f"Swap growing ~{swap_rate:.1f} GB/day under elevated pressure",
            "Growing swap plus kernel pressure is the thrash pattern — the #1 SSD write driver.",
            "Fully quit (Cmd+Q) agentic IDEs, or restart to drain swap."))
    sy = report.system
    cfg_up = config.get("uptime", {})
    if (sy.available and sy.uptime_days is not None and report.swap is not None
            and sy.uptime_days >= cfg_up.get("warn_days", 14)
            and report.swap.used_mb / 1024 >= config["swap"]["warn_gb"]):
        findings.append(_f("monitor", "warn", "uptime.restart_hint",
            f"Uptime {sy.uptime_days:.0f} days with {report.swap.used_mb / 1024:.1f} GB swap",
            "A restart drains swap — the cheapest recovery there is.",
            "Restart when convenient."))

    # --- Throttle / battery / writerate ---
    cfg_th = config.get("thermal", {})
    if (sy.available and sy.cpu_speed_limit is not None
            and sy.cpu_speed_limit < cfg_th.get("warn_below", 100)):
        findings.append(_f("monitor", "warn", "thermal.throttling",
            f"CPU throttled to {sy.cpu_speed_limit}%",
            "Thermal or power limits are cutting compute — correlate with swap/write storms.",
            "Check ventilation and what's driving the load."))
    cfg_bat = config.get("battery", {})
    if (sy.available and sy.battery_present
            and sy.battery_max_capacity_pct is not None
            and sy.battery_max_capacity_pct < cfg_bat.get("capacity_info_pct", 90)):
        findings.append(_f("monitor", "info", "battery.wear",
            f"Battery max capacity {sy.battery_max_capacity_pct}% ({sy.battery_cycle_count} cycles)",
            "Sustained agent workloads accelerate cycle burn; tracked monthly.",
            "Nothing to do — informational."))
    wr = report.writerate
    cfg_wr = config.get("writerate", {})
    if (wr.available and wr.mb_per_s is not None
            and wr.mb_per_s >= cfg_wr.get("warn_mb_s", 200)):
        findings.append(_f("monitor", "warn", "writerate.storm",
            f"Write rate {wr.mb_per_s:.0f} MB/s right now",
            "Sustained storms are usually indexing loops or snapshot churn.",
            "Check Activity Monitor's Disk tab for the culprit."))

    # --- Crash frequency ---
    cr = report.crashes
    cfg_cr = config.get("crashes", {})
    if cr.available:
        limit = cfg_cr.get("warn_weekly", 3)
        for app, count in cr.weekly.items():
            if count > limit:
                findings.append(_f("monitor", "warn", "crashes.frequent",
                    f"{app} crashed {count}× in 7 days",
                    "Mid-run crashes destroy agent context; frequent crashes signal resource exhaustion.",
                    f"Check ~/Library/Logs/DiagnosticReports for {app} reports."))
                break  # one finding is enough

    # --- External drives ---
    for ext in report.external_smart:
        if not ext.available:
            continue
        if ((ext.health and ext.health != "PASSED")
                or (ext.media_errors or 0) > 0
                or (ext.critical_warning or 0) != 0):
            findings.append(_f("monitor", "critical", "smart.external_unhealthy",
                f"External drive {ext.model or 'unknown'} unhealthy",
                f"health {ext.health or '?'} · media errors {ext.media_errors} · "
                f"critical warning 0x{(ext.critical_warning or 0):02x}",
                "This is your archive — verify backups and replace the drive."))

    return findings


def health_score(findings: list[Finding]) -> int:
    score = 100
    for f in findings:
        if f.severity == "critical":
            score -= 25
        elif f.severity == "warn":
            score -= 8
    return max(0, score)


def grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _swap_rate_gb_day(history: list[HealthReport]) -> float | None:
    """Least-squares slope of swap used (GB/day) across history entries."""
    pts: list[tuple[float, float]] = []
    for r in history:
        if r.swap is None:
            continue
        try:
            t = datetime.fromisoformat(r.timestamp).timestamp() / 86400.0
        except ValueError:
            continue
        pts.append((t, r.swap.used_mb / 1024))
    if len(pts) < 2:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    denom = sum((p[0] - mx) ** 2 for p in pts)
    if denom == 0:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / denom


def domain_statuses(findings: list[Finding],
                    report: HealthReport) -> dict[str, str]:
    """Per-domain ok|warn|critical|unknown. unknown = no findings AND the
    domain's collectors were unavailable (never confuse absence of data
    with absence of problems)."""
    collector_ok = {
        "drive": report.smart.available,
        "backup": report.backup.available,
        "headroom": report.disk is not None or report.apfs.available,
        "memory": report.swap is not None or report.pressure.available,
        "processes": not report.processes.note,
        "state": bool(report.statedirs.dirs),
        "stability": report.crashes.available or report.system.available,
        "telemetry": report.writerate.available or report.system.available,
    }
    rank = {"ok": 0, "warn": 1, "critical": 2}
    out: dict[str, str] = {}
    for domain in DOMAINS:
        worst = "ok"
        for f in findings:
            for prefix, d in _DOMAIN_BY_PREFIX.items():
                if f.code.startswith(prefix) and d == domain:
                    sev = f.severity if f.severity in rank else "ok"
                    if rank[sev] > rank[worst]:
                        worst = sev
        if worst == "ok" and not collector_ok.get(domain, True):
            worst = "unknown"
        out[domain] = worst
    return out
