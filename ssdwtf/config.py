from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "swap": {"warn_gb": 8.0, "crit_gb": 16.0},
    "disk": {"warn_free_pct": 15.0, "crit_free_pct": 10.0,
             "mount": "/System/Volumes/Data"},
    "procs": {"ghost_days": 3.0, "warn_count": 20,
              "leak_warn_mb_h": 100, "leak_window_h": 6},
    "state": {"vscdb_warn_gb": 2.0, "growth_warn_gb_day": 1.0,
              "total_warn_gb": 20.0},
    "smart": {"device": "/dev/disk0", "writes_warn_gb_day": 300.0,
              "external_devices": []},
    "alerts": {"enabled": True, "cooldown_hours": 24.0,
               "cooldown_critical_hours": 4.0},
    "watch": {"interval_minutes": 60, "fast_interval_minutes": 5},
    "clean": {"node_stale_days": 30, "caches_top_n": 10, "caches_min_mb": 500},
    "projects": [],
    "tiers": {"fast": ["smart", "swap", "disk", "processes", "pressure",
                       "system", "writerate", "backup", "retention",
                       "launchd", "spotlight", "mcp"],
              "slow": ["statedirs", "apfs", "crashes", "churn",
                       "fds", "secrets", "logs", "gitwatch"]},
    "pressure": {"sustained_min": 10},
    "apfs": {"snapshot_warn_days": 7},
    "backup": {"enabled": True, "warn_hours": 48, "crit_hours": 168},
    "crashes": {"warn_weekly": 3,
                "apps": ["Cursor", "Code", "Claude", "Windsurf"]},
    "thermal": {"warn_below": 100},
    "uptime": {"warn_days": 14},
    "writerate": {"device": "disk0", "warn_mb_s": 200},
    "battery": {"capacity_info_pct": 90},
    "churn": {"warn_turnover": 20, "warn_gb": 5},
    "fds": {"warn_count": 4000},
    "mcp": {"config_path": "~/Library/Application Support/Claude/claude_desktop_config.json"},
    "secrets": {"enabled": False},
    "spotlight": {"warn_cpu_pct": 50},
    "logs": {"warn_gb_day": 0.5, "extra_dirs": []},
    "git": {"repos": [], "warn_changes": 50, "warn_unpushed": 10},
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
