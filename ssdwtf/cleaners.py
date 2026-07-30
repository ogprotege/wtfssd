from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .collectors._run import run_cmd
from .collectors.statedirs import dir_size_bytes


@dataclass
class CleanupItem:
    path: str
    size_bytes: int


@dataclass
class CleanAction:
    path: str
    size_bytes: int
    action: str
    error: str | None = None


@dataclass
class CleanResult:
    target_id: str
    applied: bool
    skipped_reason: str | None = None
    actions: list[CleanAction] = field(default_factory=list)
    freed_bytes: int = 0


@dataclass
class CleanupTarget:
    id: str
    title: str
    description: str
    risk: str  # "safe" | "moderate" | "high"
    guard_app: str | None
    backup_first: bool
    collect: Callable[[Path, dict], list[CleanupItem]]


PROTECTED = ("Documents", "Desktop", "Movies", "Music", "Pictures")


def is_denied(path: Path, home: Path) -> bool:
    try:
        resolved = path.resolve()
        resolved.relative_to(home.resolve())
    except (ValueError, OSError):
        return True
    if resolved == home.resolve():
        return True
    rel = resolved.relative_to(home.resolve())
    return bool(rel.parts) and rel.parts[0] in PROTECTED


def _items(paths: list[Path]) -> list[CleanupItem]:
    return [CleanupItem(str(p), dir_size_bytes(p)) for p in paths if p.exists()]


def _subdirs(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return [p for p in base.iterdir()]


def _existing(base: Path, names: list[str]) -> list[Path]:
    return [base / n for n in names if (base / n).exists()]


# --- target collectors: (home, config) -> [CleanupItem] ---

def _cursor_caches(home: Path, cfg: dict) -> list[CleanupItem]:
    base = home / "Library/Application Support/Cursor"
    return _items(_existing(base, ["Cache", "CachedData", "CachedExtensionVSIXs",
                                   "Code Cache", "logs", "Service Worker"]))


def _cursor_vscdb_backups(home: Path, cfg: dict) -> list[CleanupItem]:
    gs = home / "Library/Application Support/Cursor/User/globalStorage"
    if not gs.is_dir():
        return []
    return _items(sorted(gs.glob("state.vscdb.backup*")))


def _cursor_vscdb(home: Path, cfg: dict) -> list[CleanupItem]:
    return _items([home / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"])


def _cursor_snapshots(home: Path, cfg: dict) -> list[CleanupItem]:
    packs: list[Path] = []
    for root in (home / ".cursor",
                 home / "Library/Application Support/Cursor/CachedData"):
        if root.is_dir():
            packs.extend(root.rglob("*.pack"))
    return _items([p for p in packs if p.is_file()])


def _claude_caches(home: Path, cfg: dict) -> list[CleanupItem]:
    base = home / "Library/Application Support/Claude"
    return _items(_existing(base, ["Cache", "CachedData", "Code Cache", "logs"]))


def _xcode_deriveddata(home: Path, cfg: dict) -> list[CleanupItem]:
    return _items(_subdirs(home / "Library/Developer/Xcode/DerivedData"))


def _xcode_devicesupport(home: Path, cfg: dict) -> list[CleanupItem]:
    return _items(_subdirs(home / "Library/Developer/Xcode/iOS DeviceSupport"))


def _user_caches(home: Path, cfg: dict) -> list[CleanupItem]:
    caches = home / "Library/Caches"
    min_bytes = int(cfg.get("clean", {}).get("caches_min_mb", 500)) * 1024 * 1024
    top_n = int(cfg.get("clean", {}).get("caches_top_n", 10))
    sized = [(d, dir_size_bytes(d)) for d in _subdirs(caches) if d.is_dir()]
    big = sorted(((d, s) for d, s in sized if s >= min_bytes),
                 key=lambda t: t[1], reverse=True)[:top_n]
    return [CleanupItem(str(d), s) for d, s in big]


def _node_modules_stale(home: Path, cfg: dict) -> list[CleanupItem]:
    days = int(cfg.get("clean", {}).get("node_stale_days", 30))
    cutoff = time.time() - days * 86400
    found: list[Path] = []
    for root in cfg.get("projects", []):
        root_path = Path(root).expanduser()
        if not root_path.is_dir():
            continue
        for nm in root_path.rglob("node_modules"):
            if nm.is_dir() and nm.stat().st_mtime < cutoff:
                if "node_modules" not in nm.parent.parts:  # top-level only
                    found.append(nm)
    return _items(found)


def _trash_contents(home: Path, cfg: dict) -> list[CleanupItem]:
    return _items(_subdirs(home / ".Trash"))


TARGETS: dict[str, CleanupTarget] = {t.id: t for t in [
    CleanupTarget("cursor-caches", "Cursor caches & logs",
                  "Regenerable Cursor cache/log directories", "safe",
                  "Cursor.app", False, _cursor_caches),
    CleanupTarget("cursor-vscdb-backups", "Cursor chat DB backups",
                  "Backups of the Cursor chat database", "moderate",
                  "Cursor.app", False, _cursor_vscdb_backups),
    CleanupTarget("cursor-vscdb", "Cursor chat database",
                  "state.vscdb itself — deletes local chat history (backed up first)",
                  "high", "Cursor.app", True, _cursor_vscdb),
    CleanupTarget("cursor-snapshots", "Cursor indexing snapshots",
                  "*.pack snapshot files (they regenerate; fix churn with optimize ignore)",
                  "moderate", "Cursor.app", False, _cursor_snapshots),
    CleanupTarget("claude-caches", "Claude caches & logs",
                  "Regenerable Claude cache/log directories", "safe",
                  "Claude.app", False, _claude_caches),
    CleanupTarget("xcode-deriveddata", "Xcode DerivedData",
                  "Build products; Xcode rebuilds as needed", "safe",
                  None, False, _xcode_deriveddata),
    CleanupTarget("xcode-devicesupport", "Xcode iOS DeviceSupport",
                  "Old device symbol caches", "safe",
                  None, False, _xcode_devicesupport),
    CleanupTarget("user-caches", "Largest user caches",
                  "Biggest ~/Library/Caches subdirs (regenerable)", "moderate",
                  None, False, _user_caches),
    CleanupTarget("node-modules-stale", "Stale node_modules",
                  "node_modules untouched for clean.node_stale_days under config projects",
                  "moderate", None, False, _node_modules_stale),
    CleanupTarget("trash", "Empty Trash",
                  "Permanently deletes Trash contents", "high",
                  None, False, _trash_contents),
]}


def list_targets() -> list[CleanupTarget]:
    return list(TARGETS.values())


def get_target(target_id: str) -> CleanupTarget | None:
    return TARGETS.get(target_id)


def _app_running(guard_app: str, runner: Callable) -> bool:
    out = runner(["pgrep", "-f", guard_app])
    return bool(out and out.strip())


def _trash_dest(path: Path, home: Path) -> Path:
    trash = home / ".Trash"
    trash.mkdir(exist_ok=True)
    dest = trash / path.name
    if dest.exists():
        dest = trash / f"{path.name}.ssdwtf-{datetime.now():%Y%m%d%H%M%S}"
    return dest


def clean_target(target_id: str, home: Path | None = None,
                 config: dict | None = None, apply: bool = False,
                 hard: bool = False, force: bool = False,
                 backup_dir: Path | None = None,
                 runner: Callable = run_cmd) -> CleanResult:
    from .config import load_config  # local import avoids cycle at module import
    home = home or Path.home()
    config = config if config is not None else load_config()[0]
    target = TARGETS[target_id]  # KeyError propagates — CLI validates first
    result = CleanResult(target_id=target_id, applied=apply)

    if apply and target.guard_app and not force and _app_running(target.guard_app, runner):
        result.skipped_reason = (f"{target.guard_app} is running — quit it first "
                                 f"(Cmd+Q) or pass --force")
        return result

    for item in target.collect(home, config):
        path = Path(item.path)
        if is_denied(path, home):
            result.actions.append(CleanAction(item.path, item.size_bytes, "denied"))
            continue
        if not apply:
            result.actions.append(CleanAction(item.path, item.size_bytes, "would-trash"))
            continue
        try:
            backed_up = False
            if target.backup_first:
                if backup_dir is None:
                    from .config import data_dir
                    backup_dir = data_dir() / "backups" / f"{datetime.now():%Y%m%d-%H%M%S}"
                backup_dir.mkdir(parents=True, exist_ok=True)
                if path.is_dir():
                    shutil.copytree(path, backup_dir / path.name)
                else:
                    shutil.copy2(path, backup_dir / path.name)
                backed_up = True
            if hard or target.id == "trash":
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                action = "deleted"
            else:
                shutil.move(str(path), str(_trash_dest(path, home)))
                action = "backed-up+trashed" if backed_up else "trashed"
            result.actions.append(CleanAction(item.path, item.size_bytes, action))
            result.freed_bytes += item.size_bytes
        except OSError as exc:
            result.actions.append(CleanAction(item.path, item.size_bytes, "error",
                                              error=str(exc)))
    return result
