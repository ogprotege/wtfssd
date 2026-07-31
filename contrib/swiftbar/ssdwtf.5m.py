#!/usr/bin/env python3
"""ssdwtf menu-bar plugin for SwiftBar/xbar.

Menu bar: SSD:<grade> colored by worst severity.
Dropdown: score, ten domains, top findings, actions.
Refresh: every 5 minutes (the .5m. in the filename). No mutation: actions
only run read-only scans or open Terminal for the user.

Test hook: SSDWTF_JSON env var supplies a canned scan payload.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__))))

_COLORS = {"critical": "red", "warn": "yellow", "ok": "green",
           "unknown": "gray", "info": "blue"}
_MARKS = {"ok": "✅", "warn": "⚠️", "critical": "🔴", "unknown": "❔"}


def _payload() -> dict:
    override = os.environ.get("SSDWTF_JSON")
    if override:
        return json.loads(override)
    exe = shutil.which("ssdwtf")
    cmd = ([exe] if exe else
           [sys.executable, "-m", "ssdwtf"]) + [
        "scan", "--fast", "--json", "--no-history"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                         cwd=None if exe else _REPO_ROOT)
    return json.loads(out.stdout)


def _scan_action() -> str:
    """Menu row for a full scan, mirroring _payload's launch fallback."""
    if shutil.which("ssdwtf"):
        return "Run full scan | bash=ssdwtf param1=scan terminal=true"
    cmd = (f"cd {shlex.quote(_REPO_ROOT)} && "
           f"{shlex.quote(sys.executable)} -m ssdwtf scan; read -r")
    return ('Run full scan | bash="/bin/bash" param1=-lc '
            f'param2="{cmd}" terminal=true')


def main() -> None:
    try:
        data = _payload()
        if not isinstance(data, dict):
            raise ValueError("payload is not a JSON object")
        findings = [f for f in data.get("findings", [])
                    if isinstance(f, dict)]
        rank = {"critical": 2, "warn": 1, "info": 0}
        worst = "ok"
        for f in findings:
            if rank.get(f.get("severity"), 0) > rank.get(worst, 0):
                worst = f["severity"]
        grade = data.get("grade", "?")
        lines = [f"SSD:{grade} | color={_COLORS.get(worst, 'green')}", "---",
                 f"Health {data.get('score', '?')}/100 ({grade})"]
        domains = data.get("domains", {})
        if isinstance(domains, dict) and domains:
            lines.append("---")
            for name, status in domains.items():
                lines.append(f"{_MARKS.get(status, '❔')} {name} | "
                             f"color={_COLORS.get(status, 'gray')}")
        if findings:
            lines.append("---")
            order = {"critical": 0, "warn": 1, "info": 2}
            for f in sorted(findings,
                            key=lambda f: order.get(f.get("severity"), 3))[:5]:
                sev = str(f.get("severity", "?")).upper()
                lines.append(f"[{sev}] {str(f.get('title', ''))[:70]}")
        lines.append("---")
        lines.append(_scan_action())
        lines.append("Refresh | refresh=true")
    except Exception:
        print("SSD:? | color=gray")
        print("---")
        print("ssdwtf scan failed — is the package installed?")
        raise SystemExit(0)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
