from __future__ import annotations

from .collectors.statedirs import vscdb_size_bytes
from .history import gb_written_per_day, state_growth_gb_per_day
from .models import Finding, HealthReport

GB = 1e9


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
        if smart.available_spare is not None and smart.available_spare < 100:
            findings.append(_f("monitor", "critical", "smart.spare_low",
                "Available spare below 100%",
                f"Available spare: {smart.available_spare}%",
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
        from datetime import datetime
        if datetime.fromisoformat(report.timestamp).day == 1:
            findings.append(_f("monitor", "info", "smart.monthly_check",
                "Monthly SSD check",
                "The habit that replaces doomscrolling: look at the drive's own accounting.",
                "`ssdwtf history` to see the wear trend."))
    except ValueError:
        pass

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
