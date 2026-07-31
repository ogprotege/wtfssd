from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from ..models import GitWatchReport, RepoStatus
from ._run import run_cmd


def parse_status(text: str) -> tuple[int, int]:
    """git status --porcelain → (uncommitted tracked changes, untracked files)."""
    uncommitted = untracked = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("??"):
            untracked += 1
        else:
            uncommitted += 1
    return uncommitted, untracked


def collect_repo(path: Path, runner: Callable = run_cmd) -> RepoStatus:
    if not (path / ".git").exists():
        return RepoStatus(path=str(path), error="not a git repository")
    status = runner(["git", "-C", str(path), "status", "--porcelain"])
    if status is None:
        return RepoStatus(path=str(path), error="git status failed")
    uncommitted, untracked = parse_status(status)
    remotes = runner(["git", "-C", str(path), "remote"])
    has_remote = bool(remotes and remotes.strip())
    unpushed = 0
    if has_remote:
        log = runner(["git", "-C", str(path), "log", "--branches",
                      "--not", "--remotes", "--oneline"])
        if log:
            unpushed = sum(1 for line in log.splitlines() if line.strip())
    return RepoStatus(path=str(path), uncommitted=uncommitted,
                      untracked=untracked, has_remote=has_remote,
                      unpushed=unpushed)


def collect_gitwatch(repos: list[str],
                     runner: Callable = run_cmd) -> GitWatchReport:
    """Read-only work-loss audit of configured repositories. Never fetches,
    never mutates, never raises."""
    return GitWatchReport(
        available=True,
        repos=[collect_repo(Path(r).expanduser(), runner) for r in repos])
