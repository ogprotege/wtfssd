from __future__ import annotations

import os
from pathlib import Path

from ..models import StateDir, StateDirReport

# (key, path relative to home, note)
STATE_DIRS: tuple[tuple[str, str, str], ...] = (
    ("cursor-app-support", "Library/Application Support/Cursor", "Cursor app state"),
    ("cursor-home", ".cursor", "Cursor config/extensions"),
    ("cursor-vscdb", "Library/Application Support/Cursor/User/globalStorage/state.vscdb",
     "Cursor chat database"),
    ("cursor-vscdb-backups", "Library/Application Support/Cursor/User/globalStorage",
     "Cursor chat DB backups (state.vscdb.backup*)"),
    ("claude-app-support", "Library/Application Support/Claude", "Claude app state"),
    ("claude-home", ".claude", "Claude Code transcripts/projects"),
    ("code-app-support", "Library/Application Support/Code", "VS Code state"),
    ("windsurf-app-support", "Library/Application Support/Windsurf", "Windsurf state"),
    ("xcode-deriveddata", "Library/Developer/Xcode/DerivedData", "Xcode build products"),
    ("user-caches", "Library/Caches", "User caches"),
)


def dir_size_bytes(path: Path) -> int:
    total = 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).stat().st_size
            except OSError:
                continue
    return total


def _vscdb_backups_size(global_storage: Path) -> int:
    if not global_storage.is_dir():
        return 0
    total = 0
    for entry in global_storage.glob("state.vscdb.backup*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total


def collect_statedirs(home: Path | None = None) -> StateDirReport:
    home = home or Path.home()
    dirs: list[StateDir] = []
    for key, rel, note in STATE_DIRS:
        path = home / rel
        if key == "cursor-vscdb-backups":
            size = _vscdb_backups_size(path)
            exists = size > 0
        else:
            exists = path.exists()
            size = dir_size_bytes(path) if exists else 0
        dirs.append(StateDir(key=key, path=str(path), exists=exists,
                             size_bytes=size, note=note))
    return StateDirReport(dirs=dirs, total_bytes=sum(d.size_bytes for d in dirs))


def vscdb_size_bytes(report: StateDirReport) -> int:
    for d in report.dirs:
        if d.key == "cursor-vscdb" and d.exists:
            return d.size_bytes
    return 0
