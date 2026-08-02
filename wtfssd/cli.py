from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from . import alerts, analyze, cleaners, history, metrics, optimize
from . import report as report_mod
from .collectors import apfs as apfs_col
from .collectors import backup as backup_col
from .collectors import churn as churn_col
from .collectors import crashes as crashes_col
from .collectors import disk as disk_col
from .collectors import fds as fds_col
from .collectors import gitwatch as gitwatch_col
from .collectors import launchd as launchd_col
from .collectors import logs as logs_col
from .collectors import mcp as mcp_col
from .collectors import pressure as pressure_col
from .collectors import processes as proc_col
from .collectors import retention as retention_col
from .collectors import secrets as secrets_col
from .collectors import smart as smart_col
from .collectors import smartext as smartext_col
from .collectors import spotlight as spotlight_col
from .collectors import statedirs as statedirs_col
from .collectors import swap as swap_col
from .collectors import system as system_col
from .collectors import writerate as writerate_col
from .collectors._run import run_cmd
from .config import config_path, load_config
from .models import (ApfsReport, BackupReport, ChurnReport, CrashReport,
                     FdsReport, GitWatchReport, HealthReport, LaunchdReport,
                     LogsReport, MCPReport, PressureReport, ProcessReport,
                     RetentionReport, SecretsReport, SmartReport,
                     SpotlightReport, StateDirReport, SystemReport,
                     WriteRateReport, report_to_dict)


def host_ram_gb() -> float:
    out = run_cmd(["sysctl", "-n", "hw.memsize"])
    if out is None:
        return 0.0
    try:
        return int(out.strip()) / 1e9
    except ValueError:
        return 0.0


def _resolve_tier(args: argparse.Namespace) -> str:
    """Map CLI flags to tier name. Prefer micro if both --micro and --fast."""
    if getattr(args, "micro", False):
        if getattr(args, "fast", False):
            print("warning: both --micro and --fast set; using micro",
                  file=sys.stderr)
        return "micro"
    if getattr(args, "fast", False):
        return "fast"
    return "full"


def build_report(config: dict, fast: bool = False, *,
                 tier: str | None = None,
                 bulk_state: bool = False) -> HealthReport:
    if tier is None:
        tier = "fast" if fast else "full"
    if tier not in ("micro", "fast", "full"):
        tier = "full"
    allowed = set(config.get("tiers", {}).get(tier, []))

    def want(name: str) -> bool:
        return name in allowed

    note = f"not collected (tier={tier})"
    crashes_cfg = config.get("crashes", {})

    include_bulk = bulk_state or bool(
        config.get("state", {}).get("include_bulk_default", False))

    return HealthReport(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        host_ram_gb=host_ram_gb(),
        smart=(smart_col.collect_smart(config["smart"]["device"])
               if want("smart")
               else SmartReport(available=False, error=note)),
        swap=(swap_col.collect_swap() if want("swap") else None),
        disk=(disk_col.collect_disk(config["disk"]["mount"])
              if want("disk") else None),
        processes=(proc_col.collect_processes(config["procs"]["ghost_days"])
                   if want("processes")
                   else ProcessReport(note=note)),
        statedirs=(statedirs_col.collect_statedirs(include_bulk=include_bulk)
                   if want("statedirs")
                   else StateDirReport(note=note)),
        pressure=(pressure_col.collect_pressure() if want("pressure")
                  else PressureReport(available=False, error=note)),
        system=(system_col.collect_system() if want("system")
                else SystemReport(available=False, error=note)),
        apfs=(apfs_col.collect_apfs(config["disk"]["mount"]) if want("apfs")
              else ApfsReport(available=False, error=note)),
        backup=(backup_col.collect_backup()
                if want("backup") and config.get("backup", {}).get("enabled", True)
                else BackupReport(
                    available=False,
                    error=(note if not want("backup")
                           else "not collected (backup.enabled=false)"))),
        crashes=(crashes_col.collect_crashes(crashes_cfg.get("apps", []))
                 if want("crashes")
                 else CrashReport(available=False, error=note)),
        writerate=(writerate_col.collect_writerate(
                       config.get("writerate", {}).get("device", "disk0"))
                   if want("writerate")
                   else WriteRateReport(available=False, error=note)),
        external_smart=([smartext_col.collect_smart_external(d)
                         for d in config["smart"].get("external_devices", [])]
                        if want("smart") else []),
        retention=(retention_col.collect_retention() if want("retention")
                   else RetentionReport(available=False, error=note)),
        launchd=(launchd_col.collect_launchd() if want("launchd")
                 else LaunchdReport(available=False, error=note)),
        spotlight=(spotlight_col.collect_spotlight() if want("spotlight")
                   else SpotlightReport(available=False, error=note)),
        mcp=(mcp_col.collect_mcp() if want("mcp")
             else MCPReport(available=False, error=note)),
        churn=(churn_col.collect_churn() if want("churn")
               else ChurnReport(available=False, error=note)),
        fds=(fds_col.collect_fds() if want("fds")
             else FdsReport(available=False, error=note)),
        secrets=(secrets_col.collect_secrets(
                    enabled=config.get("secrets", {}).get("enabled", False))
                 if want("secrets")
                 else SecretsReport(available=False, error=note)),
        logs=(logs_col.collect_logs(
                extra_dirs=tuple(config.get("logs", {}).get("extra_dirs", [])))
              if want("logs")
              else LogsReport(available=False, error=note)),
        gitwatch=(gitwatch_col.collect_gitwatch(
                    config.get("git", {}).get("repos", []))
                  if want("gitwatch")
                  else GitWatchReport(available=False, error=note)),
    )


def _exit_code(findings: list) -> int:
    severities = {f.severity for f in findings}
    if "critical" in severities:
        return 2
    if "warn" in severities:
        return 1
    return 0


def _run_scan(config: dict, use_history: bool,
              fast: bool = False, *,
              tier: str | None = None,
              bulk_state: bool = False) -> tuple[HealthReport, list, int]:
    if tier is None:
        tier = "fast" if fast else "full"
    rep = build_report(config, tier=tier, bulk_state=bulk_state)
    if use_history:
        history.append_history(rep)
        metrics.record(rep)
    hist = history.load_history()
    findings = analyze.analyze(rep, hist, config,
                               metrics_path=metrics.db_path() if use_history else None)
    return rep, findings, _exit_code(findings)


def cmd_scan(args: argparse.Namespace) -> int:
    config, warn = load_config()
    if warn:
        print(f"warning: {warn}", file=sys.stderr)
    tier = _resolve_tier(args)
    bulk_state = bool(getattr(args, "bulk_state", False))
    rep, findings, code = _run_scan(config, use_history=not args.no_history,
                                    tier=tier, bulk_state=bulk_state)
    if args.json:
        print(report_mod.render_json(rep, findings))
    else:
        print(report_mod.render_text(rep, findings))
    return code


def cmd_watch(args: argparse.Namespace) -> int:
    config, warn = load_config()
    if warn:
        print(f"warning: {warn}", file=sys.stderr)
    tier = _resolve_tier(args)
    bulk_state = bool(getattr(args, "bulk_state", False))
    if args.once:
        rep, findings, code = _run_scan(config, use_history=True, tier=tier,
                                        bulk_state=bulk_state)
        notified = alerts.alert(findings, config)
        for f in notified:
            print(f"notified: [{f.severity}] {f.title}")
        print(f"health {analyze.health_score(findings)}/100 "
              f"({analyze.grade(analyze.health_score(findings))}) · "
              f"{len(findings)} finding(s), {len(notified)} notified")
        return code
    interval = args.interval or config["watch"]["interval_minutes"]
    print(f"wtfssd watching every {interval} min — Ctrl-C to stop")
    while True:
        rep, findings, _ = _run_scan(config, use_history=True, tier=tier,
                                     bulk_state=bulk_state)
        notified = alerts.alert(findings, config)
        print(f"[{rep.timestamp}] health "
              f"{analyze.health_score(findings)}/100 · "
              f"{len(notified)} notification(s)")
        time.sleep(interval * 60)


def cmd_clean(args: argparse.Namespace) -> int:
    config, warn = load_config()
    if warn:
        print(f"warning: {warn}", file=sys.stderr)
    target_ids = args.targets or [t.id for t in cleaners.list_targets()
                                  if t.risk == "safe"]
    for tid in target_ids:
        target = cleaners.get_target(tid)
        if target is None:
            print(f"unknown target: {tid} "
                  f"(known: {', '.join(sorted(cleaners.TARGETS))})")
            return 3
        res = cleaners.clean_target(tid, config=config, apply=args.apply,
                                    hard=args.hard, force=args.force)
        if args.json:
            print(json.dumps({
                "target": res.target_id, "applied": res.applied,
                "skipped_reason": res.skipped_reason,
                "freed_bytes": res.freed_bytes,
                "actions": [a.__dict__ for a in res.actions],
            }, indent=2))
            continue
        print(f"== {target.title} [{target.risk}] ==")
        if res.skipped_reason:
            print(f"  SKIPPED: {res.skipped_reason}")
        if not res.actions:
            print("  nothing found")
        for a in res.actions:
            line = f"  {a.action:<18} {report_mod.format_bytes(a.size_bytes):>10}  {a.path}"
            print(line)
            if a.error:
                print(f"      error: {a.error}")
        if res.applied:
            print(f"  freed: {report_mod.format_bytes(res.freed_bytes)}")
        else:
            total = sum(a.size_bytes for a in res.actions)
            print(f"  dry-run — would free {report_mod.format_bytes(total)} "
                  f"(pass --apply)")
    return 0


def cmd_optimize(args: argparse.Namespace) -> int:
    if args.opt_command == "ignore":
        roots = [Path(p) for p in args.paths] or [Path.cwd()]
        for root in roots:
            path, added = optimize.merge_ignore_file(root)
            if added:
                print(f"{path}: added {len(added)} rule(s): {', '.join(added)}")
            else:
                print(f"{path}: already up to date")
        return 0
    if args.opt_command == "headroom":
        config, _ = load_config()
        d = disk_col.collect_disk(config["disk"]["mount"])
        if d is None:
            print("disk info unavailable")
            return 3
        print(f"free: {d.pct_free:.0f}% ({d.avail_gb:.0f} GB) — floor: 15–25%")
        if d.pct_free < 15:
            print("below the floor. Biggest monitored consumers:")
            sd = statedirs_col.collect_statedirs(include_bulk=True)
            for entry in sorted(sd.dirs, key=lambda e: e.size_bytes,
                                reverse=True)[:5]:
                if entry.exists:
                    print(f"  {report_mod.format_bytes(entry.size_bytes):>10}  "
                          f"{entry.key}")
            print("see: wtfssd clean")
        return 0
    if args.opt_command == "install-agent":
        config, _ = load_config()
        mode = getattr(args, "mode", None) or config.get(
            "watch", {}).get("agent_mode", "hourly")
        interval = int(config.get("watch", {}).get(
            "interval_minutes", 60)) * 60
        fast_interval = int(config.get("watch", {}).get(
            "fast_interval_minutes", 15)) * 60
        if mode == "none":
            print("agent_mode=none: nothing installed; use on-demand "
                  "`wtfssd scan` / `watch`")
            return 0
        if mode == "both":
            print(optimize.WARN_BOTH)
        results = optimize.install_agents(
            mode,
            interval_seconds=interval,
            fast_interval_seconds=fast_interval,
        )
        for path, loaded in results:
            print(f"wrote {path}")
            print("loaded with launchctl" if loaded else
                  f"not loaded — run: launchctl bootstrap gui/$(id -u) {path}")
        return 0
    if args.opt_command == "uninstall-agent":
        removed = optimize.uninstall_agent()
        fast_removed = optimize.uninstall_agent(label="com.wtfssd.watch.fast")
        n = int(removed) + int(fast_removed)
        print(f"{n} agent(s) removed" if n else "no agent installed")
        return 0
    return 3


def cmd_history(args: argparse.Namespace) -> int:
    entries = history.load_history(limit=args.last)
    if args.json:
        print(json.dumps([report_to_dict(r) for r in entries], indent=2))
    else:
        print(report_mod.render_history(entries))
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    config, warn = load_config()
    if warn:
        print(f"warning: {warn}", file=sys.stderr)
    rep, findings, code = _run_scan(
        config, use_history=True, tier=_resolve_tier(args))
    days = args.days
    stats = {
        "days": days,
        "scans": len(history.load_history(limit=None)),
        "domains": analyze.domain_statuses(findings, rep),
        "tb_written_delta": None,
        "gb_written_per_day": history.gb_written_per_day(
            history.load_history()),
        "swap_used_gb": rep.swap.used_mb / 1024 if rep.swap else None,
        "state_total_gb": (rep.statedirs.total_bytes / 1e9
                           if rep.statedirs.dirs else None),
        "logs_gb_per_day": metrics.rate_per_day("logs.total_gb", days=days),
        "backup_age_hours": (rep.backup.last_backup_age_hours
                             if rep.backup.available else None),
    }
    series = metrics.series("smart.tb_written", days=days)
    if len(series) >= 2:
        stats["tb_written_delta"] = series[-1][1] - series[0][1]
    if args.json:
        print(json.dumps({"stats": stats, "findings": [
            {"severity": f.severity, "code": f.code, "title": f.title}
            for f in findings]}, indent=2, default=str))
    else:
        print(report_mod.render_digest(rep, findings, stats))
    return code


def cmd_config(args: argparse.Namespace) -> int:
    if args.path:
        print(config_path())
        return 0
    config, warn = load_config()
    if warn:
        print(f"warning: {warn}", file=sys.stderr)
    print(json.dumps(config, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wtfssd",
        description=(
            "macOS CLI: diagnose agentic-IDE disk/swap/process pressure, "
            "alert, clean regenerable junk, and reduce indexer churn. "
            "See COMMANDS.md for workflows."
        ),
        epilog="Common: wtfssd scan | wtfssd clean | wtfssd optimize install-agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True,
                                metavar="command")

    # Shared tier flags (attached to scan / watch / digest)
    def _add_tier_flags(ap: argparse.ArgumentParser) -> None:
        ap.add_argument(
            "--micro", action="store_true",
            help="cheapest pass: swap, free disk, pressure, IDE process count "
                 "(~0.1s; no SMART, no directory walks, no iostat)",
        )
        ap.add_argument(
            "--fast", action="store_true",
            help="medium pass: micro + SMART, system, backup, retention, "
                 "launchd, spotlight, MCP (no statedirs walks, no writerate)",
        )
        ap.add_argument(
            "--bulk-state", action="store_true", dest="bulk_state",
            help="with full scan: also size Xcode/Docker/Caches/models "
                 "(slow; default full is AI-tool state only)",
        )

    p = sub.add_parser(
        "scan",
        help="diagnose machine health (SMART, swap, state, processes, …)",
        description="Run collectors, score findings, print a report. "
                    "Default is a full forensic pass.",
    )
    p.add_argument("--json", action="store_true",
                   help="print machine-readable JSON instead of tables")
    p.add_argument("--no-history", action="store_true",
                   help="do not append history.jsonl or metrics.db")
    _add_tier_flags(p)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser(
        "watch",
        help="run a scan and notify on new/escalated findings",
        description="Same collectors as scan, plus Notification Center alerts "
                    "(warn/critical). Use --once from LaunchAgent or cron.",
    )
    p.add_argument("--once", action="store_true",
                   help="single pass then exit (for LaunchAgent / cron)")
    p.add_argument("--interval", type=int, default=None, metavar="MIN",
                   help="loop interval in minutes (default: config "
                        "watch.interval_minutes)")
    _add_tier_flags(p)
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser(
        "clean",
        help="list or reclaim regenerable caches (dry-run by default)",
        description="Never deletes without --apply. Default moves to Trash.",
    )
    p.add_argument(
        "targets", nargs="*", metavar="target",
        help="target id(s); default = all 'safe' targets. "
             "See COMMANDS.md (cursor-caches, xcode-deriveddata, …)",
    )
    p.add_argument("--apply", action="store_true",
                   help="actually move items to Trash (or delete with --hard)")
    p.add_argument("--hard", action="store_true",
                   help="permanent delete instead of Trash (requires --apply)")
    p.add_argument("--force", action="store_true",
                   help="clean even if the owning app appears to be running")
    p.add_argument("--json", action="store_true",
                   help="print JSON results per target")
    p.set_defaults(func=cmd_clean)

    p = sub.add_parser(
        "optimize",
        help="reduce churn at the source (ignore rules, headroom, agents)",
    )
    opt_sub = p.add_subparsers(dest="opt_command", required=True,
                               metavar="subcommand")
    pi = opt_sub.add_parser(
        "ignore",
        help="write/merge .cursorignore rules to keep indexers out of junk",
    )
    pi.add_argument(
        "paths", nargs="*", metavar="dir",
        help="project roots (default: current directory)",
    )
    opt_sub.add_parser(
        "headroom",
        help="show free-space floor and largest monitored consumers",
    )
    pia = opt_sub.add_parser(
        "install-agent",
        help="install one scheduled LaunchAgent (default: hourly full scan)",
        description=(
            "Default mode is hourly: one agent running "
            "`watch --once` every hour. Dual agents require an explicit "
            "--mode both (discouraged). Prefer on-demand `scan` when possible."
        ),
    )
    pia.add_argument(
        "--mode",
        choices=["hourly", "fast", "both", "none"],
        default=None,
        help="hourly (default, one full agent) | fast (one cheap agent) | "
             "both (two agents, prints a warning) | none (install nothing)",
    )
    opt_sub.add_parser(
        "uninstall-agent",
        help="remove wtfssd LaunchAgents (hourly and/or fast labels)",
    )
    p.set_defaults(func=cmd_optimize)

    p = sub.add_parser(
        "history",
        help="show trends from past scans (TB written, free space, swap, …)",
    )
    p.add_argument("--last", type=int, default=None, metavar="N",
                   help="show only the last N history rows")
    p.add_argument("--json", action="store_true",
                   help="print JSON history entries")
    p.set_defaults(func=cmd_history)

    p = sub.add_parser(
        "digest",
        help="one-look summary of recent health and key deltas",
    )
    p.add_argument("--days", type=int, default=1, metavar="N",
                   help="look-back window in days (default: 1)")
    p.add_argument("--json", action="store_true",
                   help="print JSON digest")
    p.add_argument("--fast", action="store_true",
                   help="use fast tier for the embedded scan")
    p.add_argument("--micro", action="store_true",
                   help="use micro tier for the embedded scan")
    p.set_defaults(func=cmd_digest)

    p = sub.add_parser(
        "config",
        help="show effective config or its file path",
    )
    p.add_argument("--show", action="store_true",
                   help="print full merged config as JSON (default action)")
    p.add_argument("--path", action="store_true",
                   help="print path to ~/.config/wtfssd/config.json")
    p.set_defaults(func=cmd_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 3
    except Exception as exc:  # the anti-panic tool must not panic
        print(f"wtfssd: internal error: {exc}", file=sys.stderr)
        return 3
