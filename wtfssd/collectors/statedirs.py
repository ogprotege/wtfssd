from __future__ import annotations

import os
from pathlib import Path

from ..models import StateDir, StateDirReport

# (key, path relative to home, note, category)
# AI-core: always sized on full scan when statedirs is in the tier.
AI_STATE_DIRS: tuple[tuple[str, str, str, str], ...] = (
    ("cursor-app-support", "Library/Application Support/Cursor", "Cursor app state", "ai-state"),
    ("cursor-home", ".cursor", "Cursor config/extensions", "ai-state"),
    ("cursor-vscdb", "Library/Application Support/Cursor/User/globalStorage/state.vscdb",
     "Cursor chat database", "ai-state"),
    ("cursor-vscdb-backups", "Library/Application Support/Cursor/User/globalStorage",
     "Cursor chat DB backups (state.vscdb.backup*)", "ai-state"),
    ("claude-app-support", "Library/Application Support/Claude", "Claude app state", "ai-state"),
    ("claude-home", ".claude", "Claude Code transcripts/projects", "ai-state"),
    ("code-app-support", "Library/Application Support/Code", "VS Code state", "ide-cache"),
    ("windsurf-app-support", "Library/Application Support/Windsurf", "Windsurf state", "ai-state"),
    ("zed-app-support", "Library/Application Support/Zed", "Zed editor state", "ai-state"),
    ("codex-home", ".codex", "Codex CLI state", "ai-state"),
)

# Bulk: only when include_bulk=True (--bulk-state or state.include_bulk_default).
BULK_STATE_DIRS: tuple[tuple[str, str, str, str], ...] = (
    ("jetbrains-app-support", "Library/Application Support/JetBrains", "JetBrains IDE state", "ide-cache"),
    ("ollama-models", ".ollama", "Ollama models", "models"),
    ("lmstudio-cache", ".cache/lm-studio", "LM Studio models/cache", "models"),
    ("huggingface-cache", ".cache/huggingface", "Hugging Face hub cache", "models"),
    ("mlx-cache", ".cache/mlx", "MLX model cache", "models"),
    ("docker-data", "Library/Containers/com.docker.docker", "Docker Desktop VM data", "dev-deps"),
    ("xcode-deriveddata", "Library/Developer/Xcode/DerivedData", "Xcode build products", "build-artifacts"),
    ("user-caches", "Library/Caches", "User caches", "user-caches"),
)

# Full registry for external references (cleaners docs, len checks, etc.).
STATE_DIRS: tuple[tuple[str, str, str, str], ...] = AI_STATE_DIRS + BULK_STATE_DIRS


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


def collect_statedirs(home: Path | None = None, *,
                      include_bulk: bool = False) -> StateDirReport:
    home = home or Path.home()
    registry = AI_STATE_DIRS + BULK_STATE_DIRS if include_bulk else AI_STATE_DIRS
    dirs: list[StateDir] = []
    for key, rel, note, category in registry:
        path = home / rel
        if key == "cursor-vscdb-backups":
            size = _vscdb_backups_size(path)
            exists = size > 0
        else:
            exists = path.exists()
            size = dir_size_bytes(path) if exists else 0
        dirs.append(StateDir(key=key, path=str(path), exists=exists,
                             size_bytes=size, note=note, category=category))
    # Double-count guard: an entry nested inside another tracked entry
    # (e.g. cursor-vscdb inside cursor-app-support) is reported individually
    # but excluded from the totals.
    def _nested(d: StateDir) -> bool:
        return any(o is not d and d.path.startswith(o.path + "/")
                   for o in dirs)
    counted = [d for d in dirs if d.exists and not _nested(d)]
    category_totals: dict[str, int] = {}
    for d in counted:
        category_totals[d.category] = category_totals.get(d.category, 0) + d.size_bytes
    return StateDirReport(dirs=dirs,
                          total_bytes=sum(d.size_bytes for d in counted),
                          category_totals=category_totals)


def vscdb_size_bytes(report: StateDirReport) -> int:
    for d in report.dirs:
        if d.key == "cursor-vscdb" and d.exists:
            return d.size_bytes
    return 0
