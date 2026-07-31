from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from ..models import MCPReport, MCPServer
from ._run import run_cmd
from .processes import etime_to_seconds

_CLAUDE_MARKER = "Claude.app/Contents/MacOS/Claude"


def parse_mcp_config(text: str) -> dict[str, str]:
    """claude_desktop_config.json → {server name: match string}. Tolerates
    missing/invalid config ({})."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return {}
    out: dict[str, str] = {}
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        command = str(spec.get("command", ""))
        args = " ".join(str(a) for a in spec.get("args", []))
        match = f"{command} {args}".strip()
        if match:
            out[str(name)] = match
    return out


def _basename(match: str) -> str:
    return match.split()[0].rsplit("/", 1)[-1]


def collect_mcp(config_path: Optional[Path] = None,
                runner: Callable = run_cmd,
                home: Optional[Path] = None) -> MCPReport:
    home = home or Path.home()
    config_path = config_path or (
        home / "Library/Application Support/Claude/claude_desktop_config.json")
    if not config_path.exists():
        return MCPReport(available=False,
                         error=f"no MCP config at {config_path}")
    try:
        declared = parse_mcp_config(config_path.read_text())
    except OSError as exc:
        return MCPReport(available=False, error=str(exc))

    ps = runner(["ps", "-eo", "pid,etime,rss,args"])
    if ps is None:
        return MCPReport(available=False, error="ps failed")

    procs: list[tuple[int, int, float, str]] = []  # pid, age_s, rss_mb, args
    claude_running = False
    for line in ps.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        pid_s, etime, rss_kb, args = parts
        if _CLAUDE_MARKER in args:
            claude_running = True
        try:
            procs.append((int(pid_s), etime_to_seconds(etime),
                          int(rss_kb) / 1024, args))
        except ValueError:
            continue

    servers: list[MCPServer] = []
    for name, match in sorted(declared.items()):
        token = _basename(match)
        hits = [p for p in procs if token and token in p[3]]
        servers.append(MCPServer(
            name=name, command=match,
            live_pids=len(hits),
            rss_mb=round(sum(p[2] for p in hits), 1),
            oldest_age_s=max((p[1] for p in hits), default=0),
        ))
    return MCPReport(available=True, claude_running=claude_running,
                     servers=servers)
