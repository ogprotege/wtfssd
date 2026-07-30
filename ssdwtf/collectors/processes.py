from __future__ import annotations

from typing import Callable

from ..models import GhostProcess, ProcessReport
from ._run import run_cmd

# Substrings (case-insensitive) matched against the full command path.
IDE_PATTERNS: tuple[str, ...] = (
    "cursor", "claude", "windsurf", "zed.app", "/zed ",
    "code helper", "/code.app", "visual studio code",
)


def etime_to_seconds(etime: str) -> int:
    """ps ELAPSED: [[dd-]hh:]mm:ss"""
    days = 0
    rest = etime.strip()
    if "-" in rest:
        day_part, rest = rest.split("-", 1)
        days = int(day_part)
    parts = rest.split(":")
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + int(part)
    return days * 86400 + seconds


def is_ide_process(comm: str) -> bool:
    low = comm.lower()
    if low.startswith("/system") or low.startswith("/usr") or low.startswith("/sbin"):
        return False
    return any(pat in low for pat in IDE_PATTERNS)


def parse_ps(text: str, ghost_seconds: int) -> ProcessReport:
    ghosts: list[GhostProcess] = []
    total = 0
    for line in text.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        pid, ppid, etime, rss_kb, comm = parts
        if not is_ide_process(comm):
            continue
        total += 1
        age = etime_to_seconds(etime)
        if age >= ghost_seconds:
            ghosts.append(GhostProcess(
                pid=int(pid), ppid=int(ppid), name=comm.strip(),
                age_seconds=age, rss_mb=int(rss_kb) / 1024,
            ))
    ghosts.sort(key=lambda g: g.age_seconds, reverse=True)
    return ProcessReport(ghosts=ghosts, total_ide_processes=total)


def collect_processes(ghost_days: float = 3.0,
                      runner: Callable = run_cmd) -> ProcessReport:
    text = runner(["ps", "-eo", "pid,ppid,etime,rss,comm"])
    if text is None:
        return ProcessReport(note="ps failed")
    return parse_ps(text, ghost_seconds=int(ghost_days * 86400))
