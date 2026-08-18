from __future__ import annotations

from collections import Counter
from datetime import datetime

from . import metrics
from .collectors.statedirs import vscdb_size_bytes
from .history import gb_written_per_day, state_growth_gb_per_day
from .models import Finding, HealthReport

GB = 1e9

DOMAINS: tuple[str, ...] = ("drive", "backup", "headroom", "memory",
                            "processes", "state", "stability", "telemetry",
                            "privacy", "work")

_DOMAIN_BY_PREFIX = {
    "smart.": "drive",
    "backup.": "backup",
    "disk.": "headroom", "apfs.": "headroom",
    "swap.": "memory", "pressure.": "memory", "memory.": "memory",
    "procs.": "processes",
    "state.": "state",
    "crashes.": "stability", "thermal.": "stability", "uptime.": "stability",
    "writerate.": "telemetry", "battery.": "telemetry",
    "secrets.": "privacy", "retention.": "privacy",
    "work.": "work",
    "mcp.": "processes",
    "logs.": "state",
    "launchd.": "stability", "spotlight.": "stability",
}


def _f(pillar: str, severity: str, code: str, title: str,
       detail: str, recommendation: str,
       evidence: str = "measured") -> Finding:
    return Finding(pillar=pillar, severity=severity, code=code,
                   title=title, detail=detail, recommendation=recommendation,
                   evidence=evidence)


def analyze(report: HealthReport, history: list[HealthReport],
            config: dict, metrics_path=None) -> list[Finding]:
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
            "Check monthly: `wtfssd history`."))
        rate = gb_written_per_day(history)
        if rate is not None and rate >= cfg_smart["writes_warn_gb_day"]:
            # cross-reference swap before naming a culprit: on high-RAM
            # machines the same rate is state churn / cloud sync, not thrash
            swap_gb = (report.swap.used_mb / 1024
                       if report.swap is not None else None)
            if swap_gb is not None and swap_gb < cfg_swap["warn_gb"]:
                detail = (f"Swap is low ({swap_gb:.1f} GB), so this is "
                          "not swap thrash — look at agent/tool state churn, "
                          "cloud-sync daemons, and indexers.")
                rec = ("`wtfssd clean` (dry-run) for reclaimable state; "
                       "`wtfssd optimize ignore` for indexer churn; "
                       "Activity Monitor → Disk for per-process bytes written.")
            else:
                detail = ("Sustained writes at this rate are usually swap "
                          "thrash or snapshot churn, not wear-out.")
                rec = ("Check swap (`wtfssd scan`) and add ignore rules: "
                       "`wtfssd optimize ignore`.")
            wr = report.writers
            if wr.available and wr.top:
                w0 = wr.top[0]
                detail += (f" Top visible writer: "
                           f"{w0.name.rsplit('/', 1)[-1]} "
                           f"({w0.written_bytes / 1e9:.1f} GB since it "
                           "started).")
            findings.append(_f("monitor", "warn", "smart.write_rate",
                f"High write volume: ~{rate:.0f} GB/day",
                detail, rec, evidence="derived"))

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
                "Run `wtfssd clean` and aim for 15-25% free."))
        elif free_pct < cfg_disk["warn_free_pct"]:
            findings.append(_f("monitor", "warn", "disk.low",
                f"Low free space: {free_pct:.0f}%",
                f"{report.disk.avail_gb:.0f} GB free of {report.disk.size_gb:.0f} GB.",
                "Run `wtfssd clean` to restore the 15-25% headroom floor."))

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
        # name the offenders: a bare count is unexplainable minutes later,
        # once the helper tree that produced it has exited
        families = Counter(p.name.rsplit("/", 1)[-1]
                           for p in procs.ide_procs)
        top = ", ".join(f"{name} ×{n}"
                        for name, n in families.most_common(3))
        detail = "Agentic IDEs spawn helper trees that outlive their windows."
        if top:
            detail += f" Top: {top}."
        findings.append(_f("monitor", "warn", "procs.many",
            f"{procs.total_ide_processes} IDE-related processes running",
            detail,
            "Fully quit unused IDEs; check Activity Monitor."))

    # --- Agentic state ---
    sd = report.statedirs
    vscdb_gb = vscdb_size_bytes(sd) / GB
    if vscdb_gb >= cfg_state["vscdb_warn_gb"]:
        findings.append(_f("clean", "warn", "state.vscdb_large",
            f"Cursor chat database is {vscdb_gb:.1f} GB",
            "state.vscdb grows ~1 GB/day for heavy users, with no retention policy.",
            "Quit Cursor, then `wtfssd clean cursor-vscdb-backups --apply` (and consider cursor-vscdb)."))
    total_gb = sd.total_bytes / GB
    if total_gb >= cfg_state["total_warn_gb"]:
        findings.append(_f("clean", "warn", "state.total_large",
            f"Agentic/tooling state totals {total_gb:.0f} GB",
            "Unbounded local state with no retention policy.",
            "Run `wtfssd clean` to see safe reclaim targets."))
    growth = state_growth_gb_per_day(
        history,
        min_samples=int(cfg_state.get("growth_min_samples", 4)),
        min_span_days=float(cfg_state.get("growth_min_days", 3.0)),
        max_gb_day=float(cfg_state.get("growth_max_gb_day", 50.0)),
    )
    if growth is not None and growth >= cfg_state["growth_warn_gb_day"]:
        findings.append(_f("clean", "warn", "state.growth",
            f"State growing ~{growth:.1f} GB/day",
            "At this rate a small drive fills in weeks.",
            "Constrain the indexer: `wtfssd optimize ignore` in each project root.",
            evidence="derived"))

    # --- Monthly SMART habit ---
    try:
        if datetime.fromisoformat(report.timestamp).day == 1:
            findings.append(_f("monitor", "info", "smart.monthly_check",
                "Monthly SSD check",
                "The habit that replaces doomscrolling: look at the drive's own accounting.",
                "`wtfssd history` to see the wear trend."))
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
            minutes = config.get("pressure", {}).get("sustained_min", 180)
            if metrics_path is None:
                sustained = True  # no metrics store → point-in-time fallback
            else:
                samples = metrics.series(
                    "pressure.level",
                    days=minutes / 1440.0,
                    path=metrics_path)
                if len(samples) < 3:
                    sustained = False
                else:
                    sustained = (sum(1 for _, v in samples if v >= 2)
                                 / len(samples)) >= 0.5
            if sustained:
                findings.append(_f("monitor", "warn", "pressure.warn",
                    "Memory pressure elevated (sustained)",
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
            "Fully quit (Cmd+Q) agentic IDEs, or restart to drain swap.",
            evidence="inferred"))
    sy = report.system
    cfg_up = config.get("uptime", {})
    if (sy.available and sy.uptime_days is not None and report.swap is not None
            and sy.uptime_days >= cfg_up.get("warn_days", 14)
            and report.swap.used_mb / 1024 >= config["swap"]["warn_gb"]):
        findings.append(_f("monitor", "warn", "uptime.restart_hint",
            f"Uptime {sy.uptime_days:.0f} days with {report.swap.used_mb / 1024:.1f} GB swap",
            "A restart drains swap — the cheapest recovery there is.",
            "Restart when convenient.",
            evidence="inferred"))

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

    # --- RSS leak slopes (derived from per-PID metrics history) ---
    cfg_procs2 = config.get("procs", {})
    if metrics_path is not None and report.processes.ide_procs:
        window_days = cfg_procs2.get("leak_window_h", 6) / 24.0
        threshold = cfg_procs2.get("leak_warn_mb_h", 100)
        leakers: list[tuple[str, int, float]] = []
        for proc in report.processes.ide_procs[:10]:
            rate = metrics.rate_per_day(f"procs.rss.{proc.pid}",
                                        days=window_days * 4,
                                        path=metrics_path)
            if rate is None:
                continue
            mb_per_h = rate / 24.0
            if mb_per_h >= threshold:
                leakers.append((proc.name, proc.pid, mb_per_h))
        if leakers:
            name, pid, slope = max(leakers, key=lambda t: t[2])
            findings.append(_f("monitor", "warn", "procs.leak",
                f"{len(leakers)} leaking process(es), worst: {name} +{slope:.0f} MB/h",
                f"pid {pid} keeps growing after its window should be idle — the 4.16 GB-per-closed-window pattern.",
                "Cmd+Q the owning app; if it returns, report it upstream.",
                evidence="derived"))

    # --- Snapshot churn ---
    ch = report.churn
    cfg_ch = config.get("churn", {})
    if ch.available and ch.note is None:
        turnover = ch.added + ch.removed
        size_burst = ch.added_bytes >= cfg_ch.get("warn_gb", 5) * 1e9
        if turnover >= cfg_ch.get("warn_turnover", 20) or size_burst:
            findings.append(_f("clean", "warn", "state.churn",
                f"Snapshot churn: +{ch.added} −{ch.removed} .pack files since last scan",
                f"{ch.pack_count} packs, {ch.pack_bytes / 1e9:.1f} GB now, +{ch.added_bytes / 1e9:.1f} GB new. Create-destroy churn is write volume that never shows as missing space.",
                "Constrain the indexer: `wtfssd optimize ignore` in each project root."))

    # --- File descriptors ---
    fd = report.fds
    cfg_fd = config.get("fds", {})
    if fd.available:
        limit = cfg_fd.get("warn_count", 4000)
        worst = [(app, n) for app, n in fd.per_app.items() if n >= limit]
        if worst:
            app, n = max(worst, key=lambda t: t[1])
            findings.append(_f("monitor", "warn", "procs.fds",
                f"{app} holds {n} open file descriptors",
                f"Worst single pid: {fd.max_name} ({fd.max_pid}) with {fd.max_count}. fd exhaustion causes the mysterious mid-run crash.",
                "Restart the offending app; check for file-watcher loops."))

    # --- MCP fleet ---
    mc = report.mcp
    if mc.available:
        orphans = [s for s in mc.servers
                   if s.live_pids > 0 and not mc.claude_running]
        if orphans:
            names = ", ".join(s.name for s in orphans[:5])
            findings.append(_f("monitor", "warn", "mcp.orphan",
                f"{len(orphans)} MCP server(s) alive but Claude is not running: {names}",
                "Orphaned stdio servers are structurally the same leak as ghost IDE helpers.",
                "Kill the pids or restart Claude so it reaps them."))
        elif mc.claude_running:
            dead = [s for s in mc.servers if s.live_pids == 0]
            if dead:
                findings.append(_f("monitor", "info", "mcp.dead",
                    f"{len(dead)} configured MCP server(s) have no live process",
                    ", ".join(s.name for s in dead[:5]),
                    "Check Claude Desktop's MCP logs if you expected them."))

    # --- Secrets (opt-in) ---
    se = report.secrets
    if se.available and se.enabled and se.matches:
        by_rule: dict[str, int] = {}
        for m in se.matches:
            by_rule[m.rule] = by_rule.get(m.rule, 0) + 1
        top = ", ".join(f"{r}×{n}" for r, n in
                        sorted(by_rule.items(), key=lambda t: -t[1])[:3])
        findings.append(_f("monitor", "warn", "secrets.exposed",
            f"{len(se.matches)} credential pattern(s) at rest in agent state ({top})",
            f"Example location: {se.matches[0].path}:{se.matches[0].line}. Values are never displayed or stored by wtfssd.",
            "Rotate the exposed keys; move secrets to env vars or a manager."))

    # --- Retention posture ---
    rt = report.retention
    if rt.available:
        missing = [t.tool for t in rt.tools if t.status == "absent"]
        if missing:
            findings.append(_f("optimize", "info", "retention.missing",
                f"No retention/cleanup setting found for: {', '.join(missing)}",
                "Tools without lifecycle controls accumulate unbounded state.",
                "Set cleanupPeriodDays where supported; audit the rest monthly."))

    # --- launchd persistence ---
    ld = report.launchd
    if ld.available and ld.new_since_baseline:
        findings.append(_f("monitor", "warn", "launchd.new",
            f"{len(ld.new_since_baseline)} new LaunchAgent/Daemon(s) installed",
            ", ".join(ld.new_since_baseline[:5]) + " — ghosts that survive Cmd+Q usually survive because something relaunches them.",
            "Inspect: `launchctl list | grep <name>`; remove if unwanted."))

    # --- Spotlight ---
    sp = report.spotlight
    cfg_sp = config.get("spotlight", {})
    if (sp.available and sp.mds_cpu_pct is not None
            and sp.mds_cpu_pct >= cfg_sp.get("warn_cpu_pct", 50)):
        findings.append(_f("monitor", "warn", "spotlight.storm",
            f"Spotlight indexing at {sp.mds_cpu_pct:.0f}% CPU",
            "Agents creating thousands of files trigger mds reindexing storms — a distinct write/CPU source.",
            "Consider Spotlight privacy exclusions for agent workspace dirs."))

    # --- Log growth (derived) ---
    cfg_logs = config.get("logs", {})
    if metrics_path is not None and report.logs.available:
        rate = metrics.rate_per_day("logs.total_gb",
                                    days=7, path=metrics_path)
        if rate is not None and rate >= cfg_logs.get("warn_gb_day", 0.5):
            findings.append(_f("clean", "warn", "logs.growth",
                f"Logs growing ~{rate:.1f} GB/day",
                "Verbose MCP servers and unified logging quietly write gigabytes.",
                "Check the top log dirs in the scan; quiet the noisiest tool.",
                evidence="derived"))

    # --- Work-loss protection ---
    gw = report.gitwatch
    cfg_git = config.get("git", {})
    if gw.available:
        no_remote = [r for r in gw.repos if r.error is None and not r.has_remote]
        if no_remote:
            findings.append(_f("monitor", "warn", "work.no_remote",
                f"{len(no_remote)} repo(s) have no remote configured",
                ", ".join(r.path for r in no_remote[:3]) + " — no off-machine copy exists.",
                "Add a remote and push, or confirm the repo is covered by backup."))
        dirty = [r for r in gw.repos if r.error is None
                 and r.uncommitted + r.untracked >= cfg_git.get("warn_changes", 50)]
        if dirty:
            r = max(dirty, key=lambda r: r.uncommitted + r.untracked)
            findings.append(_f("monitor", "warn", "work.uncommitted",
                f"{r.path}: {r.uncommitted} changed + {r.untracked} untracked files",
                "Large uncommitted work is one agent mistake away from loss.",
                "Commit or stash; wtfssd will never push for you."))
        unpushed = [r for r in gw.repos if r.error is None
                    and r.unpushed >= cfg_git.get("warn_unpushed", 10)]
        if unpushed:
            r = max(unpushed, key=lambda r: r.unpushed)
            findings.append(_f("monitor", "warn", "work.unpushed",
                f"{r.path}: {r.unpushed} commits not on any remote",
                "Local-only commits are single-point-of-failure work.",
                "Push when ready; wtfssd only reports."))

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


def _swap_rate_gb_day(history: list[HealthReport],
                      window_days: float = 14.0) -> float | None:
    """Least-squares slope of swap used (GB/day), trailing window only."""
    cutoff = datetime.now().timestamp() - window_days * 86400.0
    pts: list[tuple[float, float]] = []
    for r in history:
        if r.swap is None:
            continue
        try:
            t = datetime.fromisoformat(r.timestamp).timestamp() / 86400.0
        except ValueError:
            continue
        if t * 86400.0 < cutoff:
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
        "privacy": report.secrets.available or report.retention.available,
        "work": report.gitwatch.available,
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
