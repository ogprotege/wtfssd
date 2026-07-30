from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "swap": {"warn_gb": 8.0, "crit_gb": 16.0},
    "disk": {"warn_free_pct": 15.0, "crit_free_pct": 10.0,
             "mount": "/System/Volumes/Data"},
    "procs": {"ghost_days": 3.0, "warn_count": 20},
    "state": {"vscdb_warn_gb": 2.0, "growth_warn_gb_day": 1.0,
              "total_warn_gb": 20.0},
    "smart": {"device": "/dev/disk0", "writes_warn_gb_day": 300.0},
    "alerts": {"enabled": True, "cooldown_hours": 24.0},
    "watch": {"interval_minutes": 60},
    "clean": {"node_stale_days": 30, "caches_top_n": 10, "caches_min_mb": 500},
    "projects": [],
}


def config_path() -> Path:
    return Path.home() / ".config" / "ssdwtf" / "config.json"


def data_dir() -> Path:
    return Path.home() / ".local" / "share" / "ssdwtf"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | None = None) -> tuple[dict[str, Any], str | None]:
    """Return (config, warning). Missing file → defaults, None. Invalid JSON →
    defaults, warning string. Never raises."""
    path = path or config_path()
    if not path.exists():
        return copy.deepcopy(DEFAULTS), None
    try:
        user = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return copy.deepcopy(DEFAULTS), f"invalid config at {path}: {exc} (using defaults)"
    if not isinstance(user, dict):
        return copy.deepcopy(DEFAULTS), f"config at {path} is not a JSON object (using defaults)"
    return deep_merge(DEFAULTS, user), None
