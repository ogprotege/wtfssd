from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..models import LogsReport, StateDir
from .statedirs import dir_size_bytes


def collect_logs(home: Optional[Path] = None,
                 extra_dirs: tuple[str, ...] = (),
                 top_n: int = 5) -> LogsReport:
    """Sizes ~/Library/Logs children + configured extra log dirs.
    Pure filesystem; never raises."""
    home = home or Path.home()
    roots: list[tuple[str, Path]] = []
    logs_root = home / "Library/Logs"
    try:
        if logs_root.is_dir():
            for child in sorted(logs_root.iterdir()):
                roots.append((f"logs/{child.name}", child))
    except OSError:
        pass
    for rel in extra_dirs:
        roots.append((rel, home / rel))

    entries: list[StateDir] = []
    total = 0
    for key, path in roots:
        try:
            if not path.exists():
                continue
            size = dir_size_bytes(path)
        except OSError:
            continue
        total += size
        entries.append(StateDir(key=key, path=str(path), exists=True,
                                size_bytes=size, category="logs"))
    entries.sort(key=lambda e: e.size_bytes, reverse=True)
    return LogsReport(available=True, total_bytes=total,
                      top=entries[:top_n])
