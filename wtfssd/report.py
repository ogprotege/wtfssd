from __future__ import annotations

import json

from .analyze import domain_statuses as analyze_domain_statuses, grade, health_score
from .models import Finding, HealthReport, report_to_dict

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_bytes(n: int | float) -> str:
    size = float(n)
    for unit in _UNITS:
        # 999.95 formats as 1000.0 — promote before rounding, not after.
        if unit == _UNITS[-1] or size < 999.95:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1000
    return f"{size:.1f} PB"


def _bar(rep: HealthReport) -> str:
    return (f"wtfssd scan — {rep.timestamp} · host RAM {rep.host_ram_gb:.0f} GB")


def domain_table(domains: dict[str, str]) -> list[str]:
    lines = ["== DOMAINS =="]
    for name, status in domains.items():
        marker = {"ok": "ok", "warn": "WARN", "critical": "CRIT",
                  "unknown": " ? "}.get(status, status)
        lines.append(f"  [{marker:>4}] {name}")
    return lines


def render_text(report: HealthReport, findings: list[Finding]) -> str:
    lines: list[str] = [_bar(report), ""]
    lines.extend(domain_table(analyze_domain_statuses(findings, report)))
    lines.append("")

    lines.append("== SSD / SMART ==")
    smart = report.smart
    if not smart.available:
        lines.append(f"  unavailable: {smart.error or 'unknown error'}")
        lines.append("  install smartmontools: brew install smartmontools")
    else:
        lines.append(f"  {smart.model or 'unknown drive'} · health {smart.health or '?'}")
        pct = f"{smart.percent_used}%" if smart.percent_used is not None else "?"
        spare = f"{smart.available_spare}%" if smart.available_spare is not None else "?"
        tb = f"{smart.tb_written:.1f} TB" if smart.tb_written is not None else "?"
        hrs = f"{smart.power_on_hours} h" if smart.power_on_hours is not None else "?"
        errs = smart.media_errors if smart.media_errors is not None else "?"
        lines.append(f"  lifetime writes {tb} over {hrs} power-on")
        lines.append(f"  wear used {pct} · available spare {spare} · media errors {errs}")
    lines.append("")

    lines.append("== STORAGE ==")
    if report.disk is None:
        lines.append("  unavailable")
    else:
        d = report.disk
        lines.append(f"  {d.mount}: {d.avail_gb:.0f} GB free of {d.size_gb:.0f} GB "
                     f"({d.pct_free:.0f}% free)")
    lines.append("")

    lines.append("== MEMORY / SWAP ==")
    if report.swap is None:
        lines.append("  unavailable")
    else:
        s = report.swap
        enc = " (encrypted)" if s.encrypted else ""
        lines.append(f"  swap: {s.used_mb / 1024:.1f} GB used of "
                     f"{s.total_mb / 1024:.1f} GB{enc}")
    lines.append("")

    lines.append("== PROCESSES ==")
    p = report.processes
    if p.note and not p.ghosts and p.total_ide_processes == 0:
        lines.append(f"  note: {p.note}")
    lines.append(f"  IDE-related processes: {p.total_ide_processes}")
    if p.ghosts:
        lines.append(f"  ghost processes (alive > 3 days): {len(p.ghosts)}")
        for g in p.ghosts[:5]:
            lines.append(f"    pid {g.pid} · {g.age_seconds // 86400} days · "
                         f"{g.rss_mb:.0f} MB · {g.name}")
    else:
        lines.append("  no ghost processes")
    lines.append("")

    w = report.writers
    if w.available and w.top:
        lines.append("== TOP DISK WRITERS ==")
        for proc in w.top:
            name = proc.name.rsplit("/", 1)[-1]
            hours = proc.elapsed_seconds / 3600
            lines.append(f"  {format_bytes(proc.written_bytes):>10}  "
                         f"{name} (over {hours:.1f} h alive)")
        lines.append(f"  {format_bytes(w.visible_total_bytes):>10}  "
                     f"visible total across {w.process_count} processes")
        lines.append("  note: live processes only — exited processes took "
                     "their write counters with them")
        lines.append("")

    lines.append("== AGENTIC STATE ==")
    if report.statedirs.note and not report.statedirs.dirs:
        lines.append(f"  note: {report.statedirs.note}")
    for d in report.statedirs.dirs:
        if d.exists:
            lines.append(f"  {format_bytes(d.size_bytes):>10}  {d.key} — {d.note}")
    lines.append(f"  {format_bytes(report.statedirs.total_bytes):>10}  TOTAL")
    lines.append("")

    lines.append("== FINDINGS ==")
    if not findings:
        lines.append("  none — machine looks healthy")
    order = {"critical": 0, "warn": 1, "info": 2}
    for f in sorted(findings, key=lambda f: order.get(f.severity, 3)):
        ev = f" (evidence: {f.evidence})" if f.evidence != "measured" else ""
        lines.append(f"  [{f.severity.upper()}] {f.title}{ev}")
        lines.append(f"      {f.detail}")
        lines.append(f"      → {f.recommendation}")
    lines.append("")

    score = health_score(findings)
    lines.append(f"Health: {score}/100 ({grade(score)})")
    return "\n".join(lines)


def render_json(report: HealthReport, findings: list[Finding]) -> str:
    score = health_score(findings)
    payload = {
        "report": report_to_dict(report),
        "findings": [
            {"pillar": f.pillar, "severity": f.severity, "code": f.code,
             "title": f.title, "detail": f.detail,
             "recommendation": f.recommendation, "evidence": f.evidence}
            for f in findings
        ],
        "score": score,
        "grade": grade(score),
        "domains": analyze_domain_statuses(findings, report),
    }
    return json.dumps(payload, indent=2)


def _history_tier_label(r: HealthReport) -> str:
    """Human tier for the history table. Legacy rows without scan_tier are inferred."""
    tier = getattr(r, "scan_tier", None)
    if tier in ("micro", "fast", "full"):
        label = tier
    else:
        # Pre-tier-field history: statedirs.note means skipped → not a full measure.
        if r.statedirs.note:
            label = "fast?" if r.smart.available else "micro?"
        elif not r.smart.available and r.disk is not None:
            # SMART missing but disk present — likely cheap/partial pass
            label = "partial?"
        else:
            label = "full"
    if getattr(r, "bulk_state", False) and label.startswith("full"):
        label = "full+b"
    return label


def _history_state_gb(r: HealthReport) -> str:
    """Never show 0.0 for unmeasured state (fast/micro placeholders)."""
    if r.statedirs.note:
        return "—"
    return f"{r.statedirs.total_bytes / 1e9:.1f}"


def _history_smart_tb(r: HealthReport) -> str:
    if not r.smart.available or r.smart.tb_written is None:
        return "—"
    return f"{r.smart.tb_written:.1f}"


def _history_smart_wear(r: HealthReport) -> str:
    if not r.smart.available or r.smart.percent_used is None:
        return "—"
    return f"{r.smart.percent_used}"


def render_history(history: list[HealthReport], *,
                   full_only: bool = False) -> str:
    """Trend table. Unmeasured cells are em-dash, not 0.0.

    full_only: drop micro/fast rows so STATE/SMART trends stay comparable.
    """
    rows = list(history)
    skipped = 0
    if full_only:
        kept: list[HealthReport] = []
        for r in rows:
            tier = _history_tier_label(r)
            if tier.startswith("full"):
                kept.append(r)
            else:
                skipped += 1
        rows = kept

    header = (f"{'TIMESTAMP':<20} {'TIER':<7} {'TB WRITTEN':>10} {'WEAR %':>7} "
              f"{'FREE GB':>9} {'SWAP GB':>8} {'STATE GB':>9}")
    lines = [header, "-" * len(header)]
    unmeasured_state = 0
    for r in rows:
        tier = _history_tier_label(r)
        tb = _history_smart_tb(r)
        wear = _history_smart_wear(r)
        free = f"{r.disk.avail_gb:.0f}" if r.disk else "—"
        swap = f"{r.swap.used_mb / 1024:.1f}" if r.swap else "—"
        state = _history_state_gb(r)
        if state == "—":
            unmeasured_state += 1
        lines.append(f"{r.timestamp:<20} {tier:<7} {tb:>10} {wear:>7} "
                     f"{free:>9} {swap:>8} {state:>9}")

    if not rows:
        lines.append("(no rows to show)")
    else:
        notes: list[str] = []
        if full_only and skipped:
            notes.append(f"hid {skipped} micro/fast row(s); use without "
                         f"--full-only to see them")
        if unmeasured_state and not full_only:
            notes.append(
                f"{unmeasured_state} row(s) have STATE — (not measured: "
                f"micro/fast tier). Compare STATE only across full rows.")
        if notes:
            lines.append("")
            for n in notes:
                lines.append(f"note: {n}")
    return "\n".join(lines)


def render_digest(report: HealthReport, findings: list[Finding],
                  stats: dict) -> str:
    """One-look daily summary: domains, key deltas, findings by severity."""
    lines = [f"wtfssd digest — {report.timestamp} "
             f"(window: {stats.get('days', 1)} day(s))", ""]
    lines.append(f"  scans recorded: {stats.get('scans', 0)}")
    domains = stats.get("domains", {})
    if domains:
        worst = max(domains.values(),
                    key=lambda s: {"ok": 0, "unknown": 0, "warn": 1,
                                   "critical": 2}.get(s, 0))
        lines.append(f"  domains: worst = {worst}")
    deltas = [
        ("SSD writes", stats.get("tb_written_delta"), "{:+.2f} TB"),
        ("write rate trend", stats.get("gb_written_per_day"), "{:.1f} GB/day"),
        ("swap (latest)", stats.get("swap_used_gb"), "{:.1f} GB"),
        ("state total (latest)", stats.get("state_total_gb"), "{:.1f} GB"),
        ("logs growth", stats.get("logs_gb_per_day"), "{:+.2f} GB/day"),
        ("backup age", stats.get("backup_age_hours"), "{:.0f} h"),
    ]
    for label, value, fmt in deltas:
        if value is not None:
            lines.append(f"  {label:<20} {fmt.format(value)}")
    sev = {"critical": 0, "warn": 0, "info": 0}
    for f in findings:
        sev[f.severity] = sev.get(f.severity, 0) + 1
    lines.append(f"  findings: {sev['critical']} critical · "
                 f"{sev['warn']} warn · {sev['info']} info")
    score = health_score(findings)
    lines.append(f"  health: {score}/100 ({grade(score)})")
    return "\n".join(lines)
