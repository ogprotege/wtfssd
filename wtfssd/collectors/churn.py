from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..config import data_dir as default_data_dir
from ..models import ChurnReport

_WATCH_RELS = (".cursor", "Library/Application Support/Cursor/CachedData")


def _scan_packs(home: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for rel in _WATCH_RELS:
        root = home / rel
        if not root.is_dir():
            continue
        try:
            for p in root.rglob("*.pack"):
                try:
                    p.resolve().relative_to(root.resolve())
                except (ValueError, OSError, RuntimeError):
                    continue
                try:
                    if p.is_file() and not p.is_symlink():
                        out[str(p.relative_to(home))] = p.stat().st_size
                except OSError:
                    continue
        except OSError:
            continue
    return out


def collect_churn(home: Optional[Path] = None,
                  state_path: Optional[Path] = None) -> ChurnReport:
    """Snapshot (.pack) create/destroy turnover. High turnover with stable
    total = churn: writes that never show up as missing space. Never raises."""
    home = home or Path.home()
    state_path = state_path or (default_data_dir() / "churn_state.json")
    try:
        current = _scan_packs(home)
    except Exception as exc:
        return ChurnReport(available=False, error=str(exc))

    previous: dict[str, int] = {}
    baseline_exists = False
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text())
            if not isinstance(data, dict) or "packs" not in data:
                raise TypeError("packs missing")
            packs = data["packs"]
            if not isinstance(packs, dict):
                raise TypeError("packs is not a dict")
            previous = {str(k): int(v) for k, v in packs.items()}
            baseline_exists = True
        except (json.JSONDecodeError, OSError, TypeError, AttributeError,
                ValueError):
            previous = {}

    added = sum(1 for k in current if k not in previous)
    removed = sum(1 for k in previous if k not in current)
    added_bytes = sum(v for k, v in current.items() if k not in previous)

    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"packs": current}))
    except OSError:
        pass  # state write failure must not break the scan

    return ChurnReport(
        available=True,
        pack_count=len(current),
        pack_bytes=sum(current.values()),
        added=added if baseline_exists else 0,
        removed=removed if baseline_exists else 0,
        added_bytes=added_bytes if baseline_exists else 0,
        note=None if baseline_exists else "baseline stored",
    )
