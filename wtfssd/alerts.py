from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from .collectors._run import run_cmd
from .config import data_dir as default_data_dir
from .models import Finding

Notifier = Callable[[Finding], bool]


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _osascript_notify(finding: Finding, runner: Callable = run_cmd) -> bool:
    detail = _escape(finding.detail[:200])
    title = _escape(f"wtfssd: {finding.title[:80]}")
    script = (f'display notification "{detail}" with title "{title}" '
              f'sound name "Glass"')
    # osascript exits 0 and prints nothing even when the notification fails,
    # so append a trailing `return "ok"` and require it in stdout as proof
    # the whole script ran (run_cmd returns None on empty stdout/failure).
    out = runner(["osascript", "-e", script, "-e", 'return "ok"'])
    return out is not None and "ok" in out


def notify(finding: Finding, notifier: Notifier | None = None) -> bool:
    notifier = notifier or _osascript_notify
    try:
        return bool(notifier(finding))
    except Exception:
        return False


def _state_path(state_dir: Path | None) -> Path:
    return (state_dir or default_data_dir()) / "alert_state.json"


def _load_state(state_dir: Path | None) -> dict[str, dict]:
    """Tolerates both formats: new {code: {ts, severity}} and old {code: iso}."""
    try:
        data = json.loads(_state_path(state_dir).read_text())
        if not isinstance(data, dict):
            return {}
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, dict] = {}
    for code, entry in data.items():
        if isinstance(entry, dict) and "ts" in entry:
            out[code] = {"ts": entry["ts"],
                         "severity": entry.get("severity", "warn")}
        elif isinstance(entry, str):
            out[code] = {"ts": entry, "severity": "warn"}  # legacy format
    return out


def _save_state(state: dict[str, dict], state_dir: Path | None) -> None:
    path = _state_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def alert(findings: list[Finding], config: dict,
          state_dir: Path | None = None,
          notifier: Notifier | None = None,
          now: datetime | None = None) -> list[Finding]:
    """Notify on transitions: new finding code, severity increase, or
    per-severity cooldown elapsed (critical: alerts.cooldown_critical_hours,
    warn: alerts.cooldown_hours). Info findings never notify."""
    if not config.get("alerts", {}).get("enabled", True):
        return []
    now = now or datetime.now()
    cfg = config.get("alerts", {})
    cooldowns = {
        "warn": timedelta(hours=cfg.get("cooldown_hours", 24.0)),
        "critical": timedelta(hours=cfg.get("cooldown_critical_hours", 4.0)),
    }
    rank = {"warn": 1, "critical": 2}
    state = _load_state(state_dir)
    notified: list[Finding] = []
    for f in findings:
        if f.severity not in rank:
            continue
        last = state.get(f.code)
        if last:
            try:
                elapsed = now - datetime.fromisoformat(last["ts"])
            except (ValueError, TypeError):
                elapsed = None
            same_or_lower = rank.get(last["severity"], 1) >= rank[f.severity]
            if (same_or_lower and elapsed is not None
                    and elapsed < cooldowns[f.severity]):
                continue  # still inside the cooldown for a non-escalation
        if notify(f, notifier):
            state[f.code] = {"ts": now.isoformat(), "severity": f.severity}
            notified.append(f)
    _save_state(state, state_dir)
    return notified
