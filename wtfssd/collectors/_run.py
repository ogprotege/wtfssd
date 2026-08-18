from __future__ import annotations

import subprocess
from typing import Optional


def run_cmd(argv: list[str], timeout: int = 15, *,
            allow_empty: bool = False) -> Optional[str]:
    """Run argv (no shell), return stdout as text. Returns stdout whenever the
    process ran and produced non-empty output, regardless of exit code (some
    tools, e.g. smartctl, use non-zero exit bitmasks while still printing
    valid data). Return None on any failure: missing binary, timeout, OSError,
    undecodable output, or empty stdout. allow_empty=True keeps a successful
    empty stdout as "" (needed for `git status --porcelain` on a clean tree).
    Never raises."""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError,
            UnicodeDecodeError):
        return None
    if not proc.stdout:
        if allow_empty and proc.returncode == 0:
            return ""
        return None
    return proc.stdout
