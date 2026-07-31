from __future__ import annotations

import os
import sys
from pathlib import Path

from .collectors._run import run_cmd

IGNORE_MARKER = "# wtfssd — keep the indexer out of churn"
IGNORE_LINES: list[str] = [
    "node_modules/", "dist/", "build/", ".next/", "out/",
    ".turbo/", "coverage/", "*.log",
]


def merge_ignore_file(root: Path) -> tuple[Path, list[str]]:
    path = root / ".cursorignore"
    existing: list[str] = []
    if path.exists():
        existing = path.read_text().splitlines()
    have = {ln.strip() for ln in existing}
    added = [ln for ln in IGNORE_LINES if ln not in have]
    if added:
        with path.open("a") as fh:
            if existing and existing[-1].strip():
                fh.write("\n")
            fh.write(f"{IGNORE_MARKER}\n")
            for ln in added:
                fh.write(f"{ln}\n")
    return path, added


def _program_args(fast: bool = False) -> list[str]:
    """How to invoke wtfssd: installed script if present, else python -m from source."""
    from shutil import which
    tail = ["watch", "--once"] + (["--fast"] if fast else [])
    exe = which("wtfssd")
    if exe:
        return [exe] + tail
    return [sys.executable, "-m", "wtfssd"] + tail


def _plist(label: str, interval_seconds: int, log_path: Path,
           fast: bool = False) -> str:
    args = _program_args(fast=fast)
    args_xml = "\n".join(f"        <string>{a}</string>" for a in args)
    env_xml = ""
    if args[1:2] == ["-m"]:  # source checkout → needs PYTHONPATH
        repo_root = str(Path(__file__).resolve().parent.parent)
        env_xml = f"""    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>{repo_root}</string>
    </dict>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
{env_xml}
    <key>StartInterval</key>
    <integer>{interval_seconds}</integer>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
"""


def install_agent(interval_seconds: int = 3600,
                  label: str = "com.wtfssd.watch",
                  launch_agents_dir: Path | None = None) -> tuple[Path, bool]:
    from .config import data_dir
    agents = launch_agents_dir or (Path.home() / "Library" / "LaunchAgents")
    agents.mkdir(parents=True, exist_ok=True)
    plist_path = agents / f"{label}.plist"
    log_path = data_dir() / "watch.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(_plist(label, interval_seconds, log_path))
    loaded = False
    if launch_agents_dir is None:  # only touch launchctl for a real install
        run_cmd(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"])
        run_cmd(["launchctl", "bootstrap", f"gui/{os.getuid()}",
                 str(plist_path)])
        # bootstrap prints nothing on success, and run_cmd returns None for
        # empty stdout — probe actual state instead of trusting the return.
        loaded = run_cmd(["launchctl", "print",
                          f"gui/{os.getuid()}/{label}"]) is not None
    return plist_path, loaded


def uninstall_agent(label: str = "com.wtfssd.watch",
                    launch_agents_dir: Path | None = None) -> bool:
    agents = launch_agents_dir or (Path.home() / "Library" / "LaunchAgents")
    plist_path = agents / f"{label}.plist"
    if not plist_path.exists():
        return False
    if launch_agents_dir is None:
        run_cmd(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"])
    plist_path.unlink()
    return True


def install_fast_agent(interval_seconds: int = 300,
                       label: str = "com.wtfssd.watch.fast",
                       launch_agents_dir: Path | None = None) -> tuple[Path, bool]:
    """5-minute fast-tier watcher (watch --once --fast) alongside the hourly
    full agent. Same launchctl probe semantics as install_agent."""
    from .config import data_dir
    agents = launch_agents_dir or (Path.home() / "Library" / "LaunchAgents")
    agents.mkdir(parents=True, exist_ok=True)
    plist_path = agents / f"{label}.plist"
    log_path = data_dir() / "watch-fast.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(_plist(label, interval_seconds, log_path,
                                 fast=True))
    loaded = False
    if launch_agents_dir is None:
        run_cmd(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"])
        run_cmd(["launchctl", "bootstrap", f"gui/{os.getuid()}",
                 str(plist_path)])
        loaded = run_cmd(["launchctl", "print",
                          f"gui/{os.getuid()}/{label}"]) is not None
    return plist_path, loaded
