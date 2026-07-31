from __future__ import annotations

import subprocess
from typing import Optional


def run_cmd(argv: list[str], timeout: int = 15) -> Optional[str]:
    """Run argv (no shell), return stdout as text. Returns stdout whenever the
    process ran and produced non-empty output, regardless of exit code (some
    tools, e.g. smartctl, use non-zero exit bitmasks while still printing
    valid data). Return None on any failure: missing binary, timeout, OSError,
    undecodable output, or empty stdout. Never raises."""
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
        return None
    return proc.stdout
