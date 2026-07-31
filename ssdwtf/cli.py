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
                     FdsReport, GitWatchReport, HealthReport, LogsReport,
                     SecretsReport, StateDirReport, report_to_dict)


def host_ram_gb() -> float:
    out = run_cmd(["sysctl", "-n", "hw.memsize"])
    if out is None:
        return 0.0
    try:
        return int(out.strip()) / 1e9
    except ValueError:
        return 0.0


def build_report(config: dict, fast: bool = False) -> HealthReport:
    slow = set(config.get("tiers", {}).get("slow", []))

    def want(name: str) -> bool:
        return not (fast and name in slow)

    crashes_cfg = config.get("crashes", {})
    return HealthReport(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        host_ram_gb=host_ram_gb(),
        smart=smart_col.collect_smart(config["smart"]["device"]),
        swap=swap_col.collect_swap(),
        disk=disk_col.collect_disk(config["disk"]["mount"]),
        processes=proc_col.collect_processes(config["procs"]["ghost_days"]),
        statedirs=(statedirs_col.collect_statedirs() if want("statedirs")
                   else StateDirReport(note="not collected (--fast)")),
        pressure=pressure_col.collect_pressure(),
        system=system_col.collect_system(),
        apfs=(apfs_col.collect_apfs(config["disk"]["mount"]) if want("apfs")
              else ApfsReport(available=False, error="not collected (--fast)")),
        backup=(backup_col.collect_backup()
                if want("backup") and config.get("backup", {}).get("enabled", True)
                else BackupReport(
                    available=False,
                    error=("not collected (--fast)" if not want("backup")
                           else "not collected (backup.enabled=false)"))),
        crashes=(crashes_col.collect_crashes(crashes_cfg.get("apps", []))
                 if want("crashes")
                 else CrashReport(available=False, error="not collected (--fast)")),
        writerate=writerate_col.collect_writerate(
            config.get("writerate", {}).get("device", "disk0")),
        external_smart=[smartext_col.collect_smart_external(d)
                        for d in config["smart"].get("external_devices", [])],
        retention=retention_col.collect_retention(),
        launchd=launchd_col.collect_launchd(),
        spotlight=spotlight_col.collect_spotlight(),
        mcp=mcp_col.collect_mcp(),
        churn=(churn_col.collect_churn() if want("churn")
               else ChurnReport(available=False, error="not collected (--fast)")),
        fds=(fds_col.collect_fds() if want("fds")
             else FdsReport(available=False, error="not collected (--fast)")),
        secrets=(secrets_col.collect_secrets(
                    enabled=config.get("secrets", {}).get("enabled", False))
                 if want("secrets")
                 else SecretsReport(available=False, error="not collected (--fast)")),
        logs=(logs_col.collect_logs(
                extra_dirs=tuple(config.get("logs", {}).get("extra_dirs", [])))
              if want("logs")
              else LogsReport(available=False, error="not collected (--fast)")),
        gitwatch=(gitwatch_col.collect_gitwatch(
                    config.get("git", {}).get("repos", []))
                  if want("gitwatch")
                  else GitWatchReport(available=False, error="not collected (--fast)")),
    )


def _exit_code(findings: list) -> int:
    severities = {f.severity for f in findings}
    if "critical" in severities:
        return 2
    if "warn" in severities:
        return 1
    return 0


def _run_scan(config: dict, use_history: bool,
              fast: bool = False) -> tuple[HealthReport, list, int]:
    rep = build_report(config, fast=fast)
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
    rep, findings, code = _run_scan(config, use_history=not args.no_history,
                                    fast=args.fast)
    if args.json:
        print(report_mod.render_json(rep, findings))
    else:
        print(report_mod.render_text(rep, findings))
    return code


def cmd_watch(args: argparse.Namespace) -> int:
    config, warn = load_config()
    if warn:
        print(f"warning: {warn}", file=sys.stderr)
    if args.once:
        rep, findings, code = _run_scan(config, use_history=True,
                                        fast=args.fast)
        notified = alerts.alert(findings, config)
        for f in notified:
            print(f"notified: [{f.severity}] {f.title}")
        print(f"health {analyze.health_score(findings)}/100 "
              f"({analyze.grade(analyze.health_score(findings))}) · "
              f"{len(findings)} finding(s), {len(notified)} notified")
        return code
    interval = args.interval or config["watch"]["interval_minutes"]
    print(f"ssdwtf watching every {interval} min — Ctrl-C to stop")
    while True:
        rep, findings, _ = _run_scan(config, use_history=True, fast=args.fast)
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
            sd = statedirs_col.collect_statedirs()
            for entry in sorted(sd.dirs, key=lambda e: e.size_bytes,
                                reverse=True)[:5]:
                if entry.exists:
                    print(f"  {report_mod.format_bytes(entry.size_bytes):>10}  "
                          f"{entry.key}")
            print("see: ssdwtf clean")
        return 0
    if args.opt_command == "install-agent":
        path, loaded = optimize.install_agent()
        print(f"wrote {path}")
        print("loaded with launchctl" if loaded else
              f"not loaded — run: launchctl bootstrap gui/$(id -u) {path}")
        return 0
    if args.opt_command == "uninstall-agent":
        removed = optimize.uninstall_agent()
        print("agent removed" if removed else "no agent installed")
        return 0
    return 3


def cmd_history(args: argparse.Namespace) -> int:
    entries = history.load_history(limit=args.last)
    if args.json:
        print(json.dumps([report_to_dict(r) for r in entries], indent=2))
    else:
        print(report_mod.render_history(entries))
    return 0


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
        prog="ssdwtf",
        description="Why is my Mac's SSD busy/full/'dying' — monitor, alert, "
                    "clean, optimize.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="full health report")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-history", action="store_true")
    p.add_argument("--fast", action="store_true",
                   help="fast tier only (skip slow collectors)")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("watch", help="monitor + alert loop")
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval", type=int, default=None,
                   help="minutes between passes (default: config)")
    p.add_argument("--fast", action="store_true",
                   help="fast tier only (skip slow collectors)")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("clean", help="safe cleanup (dry-run by default)")
    p.add_argument("targets", nargs="*",
                   help="target ids (default: all 'safe' targets)")
    p.add_argument("--apply", action="store_true",
                   help="actually clean (moves to Trash)")
    p.add_argument("--hard", action="store_true",
                   help="delete permanently instead of Trash")
    p.add_argument("--force", action="store_true",
                   help="clean even if the owning app is running")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_clean)

    p = sub.add_parser("optimize", help="fix churn at the source")
    opt_sub = p.add_subparsers(dest="opt_command", required=True)
    pi = opt_sub.add_parser("ignore", help="write/merge .cursorignore")
    pi.add_argument("paths", nargs="*")
    opt_sub.add_parser("headroom", help="free-space floor status + top consumers")
    opt_sub.add_parser("install-agent", help="install hourly LaunchAgent")
    opt_sub.add_parser("uninstall-agent", help="remove LaunchAgent")
    p.set_defaults(func=cmd_optimize)

    p = sub.add_parser("history", help="trend table")
    p.add_argument("--last", type=int, default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("config", help="show effective config")
    p.add_argument("--show", action="store_true")
    p.add_argument("--path", action="store_true")
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
        print(f"ssdwtf: internal error: {exc}", file=sys.stderr)
        return 3
