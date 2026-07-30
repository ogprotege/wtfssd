from __future__ import annotations

import json

from .analyze import grade, health_score
from .models import Finding, HealthReport, report_to_dict

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_bytes(n: int | float) -> str:
    size = float(n)
    for unit in _UNITS:
        if size < 1000 or unit == _UNITS[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1000
    return f"{size:.1f} PB"


def _bar(rep: HealthReport) -> str:
    return (f"ssdwtf scan — {rep.timestamp} · host RAM {rep.host_ram_gb:.0f} GB")


def render_text(report: HealthReport, findings: list[Finding]) -> str:
    lines: list[str] = [_bar(report), ""]

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
        lines.append(f"  [{f.severity.upper()}] {f.title}")
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
             "recommendation": f.recommendation}
            for f in findings
        ],
        "score": score,
        "grade": grade(score),
    }
    return json.dumps(payload, indent=2)


def render_history(history: list[HealthReport]) -> str:
    header = (f"{'TIMESTAMP':<20} {'TB WRITTEN':>10} {'WEAR %':>7} "
              f"{'FREE GB':>9} {'SWAP GB':>8} {'STATE GB':>9}")
    lines = [header, "-" * len(header)]
    for r in history:
        tb = f"{r.smart.tb_written:.1f}" if r.smart.tb_written is not None else "-"
        wear = f"{r.smart.percent_used}" if r.smart.percent_used is not None else "-"
        free = f"{r.disk.avail_gb:.0f}" if r.disk else "-"
        swap = f"{r.swap.used_mb / 1024:.1f}" if r.swap else "-"
        state = f"{r.statedirs.total_bytes / 1e9:.1f}"
        lines.append(f"{r.timestamp:<20} {tb:>10} {wear:>7} "
                     f"{free:>9} {swap:>8} {state:>9}")
    return "\n".join(lines)
