from __future__ import annotations

import inspect
from pathlib import Path
from typing import Callable

from ..models import GitWatchReport, RepoStatus
from ._run import run_cmd

# Neutralize repo-local hook / fsmonitor / auto-gc / signature helpers.
# `git -C … status` otherwise honors that repo's config. Aliases cannot
# shadow builtins (status/remote/log), so they are left alone.
_GIT_SAFE = (
    "git",
    "--no-pager",
    "-c", "core.fsmonitor=",
    "-c", "core.useBuiltinFSMonitor=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "gc.auto=0",
    "-c", "maintenance.auto=false",
    "-c", "log.showSignature=false",
    "--no-optional-locks",
    "-C",
)


def _runner_accepts_allow_empty(runner: Callable) -> bool:
    try:
        params = inspect.signature(runner).parameters
    except (TypeError, ValueError):
        return False
    if "allow_empty" in params:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())


def _git(runner: Callable, path: Path, *args: str,
         allow_empty: bool = False,
         extra_config: list[str] | None = None) -> str | None:
    argv = list(_GIT_SAFE[:-1])  # drop trailing -C so extra -c can go first
    if extra_config:
        argv.extend(extra_config)
    argv.extend(["-C", str(path), *args])
    if allow_empty and _runner_accepts_allow_empty(runner):
        return runner(argv, allow_empty=True)
    return runner(argv)


def _filter_overrides(runner: Callable, path: Path) -> list[str]:
    """Disable repo-defined clean/smudge/process filters for this call.

    `git status` otherwise runs `filter.<name>.clean` from that repo's
    config. Listing names via `git config` does not execute them.
    Disabling LFS/custom filters can make pointer files look dirty —
    safer than running repo-supplied commands."""
    text = _git(runner, path, "config", "--get-regexp", r"^filter\.",
                allow_empty=True)
    if not text:
        return []
    names: set[str] = set()
    for line in text.splitlines():
        key = line.split(None, 1)[0] if line.strip() else ""
        parts = key.split(".")
        if len(parts) >= 2 and parts[0] == "filter" and parts[1]:
            names.add(parts[1])
    extra: list[str] = []
    for name in sorted(names):
        extra.extend([
            "-c", f"filter.{name}.clean=",
            "-c", f"filter.{name}.smudge=",
            "-c", f"filter.{name}.process=",
            "-c", f"filter.{name}.required=false",
        ])
    return extra


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
    filters = _filter_overrides(runner, path)
    status = _git(runner, path, "status", "--porcelain",
                  allow_empty=True, extra_config=filters)
    if status is None:
        return RepoStatus(path=str(path), error="git status failed")
    uncommitted, untracked = parse_status(status)
    remotes = _git(runner, path, "remote")
    has_remote = bool(remotes and remotes.strip())
    unpushed = 0
    if has_remote:
        log = _git(runner, path, "log", "--branches",
                   "--not", "--remotes", "--oneline",
                   "--no-show-signature")
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
