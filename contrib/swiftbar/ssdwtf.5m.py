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


def main() -> None:
    try:
        data = _payload()
    except Exception:
        print("SSD:? | color=gray")
        print("---")
        print("ssdwtf scan failed — is the package installed?")
        raise SystemExit(0)

    findings = data.get("findings", [])
    rank = {"critical": 2, "warn": 1, "info": 0}
    worst = "ok"
    for f in findings:
        if rank.get(f.get("severity"), 0) > rank.get(worst, 0):
            worst = f["severity"]
    grade = data.get("grade", "?")
    print(f"SSD:{grade} | color={_COLORS.get(worst, 'green')}")
    print("---")
    print(f"Health {data.get('score', '?')}/100 ({grade})")
    domains = data.get("domains", {})
    if domains:
        print("---")
        for name, status in domains.items():
            print(f"{_MARKS.get(status, '❔')} {name} | color={_COLORS.get(status, 'gray')}")
    if findings:
        print("---")
        order = {"critical": 0, "warn": 1, "info": 2}
        for f in sorted(findings,
                        key=lambda f: order.get(f.get("severity"), 3))[:5]:
            print(f"[{f.get('severity', '?').upper()}] {f.get('title', '')[:70]}")
    print("---")
    print("Run full scan | bash=ssdwtf param1=scan terminal=true")
    print("Refresh | refresh=true")


if __name__ == "__main__":
    main()
