from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..models import RetentionEntry, RetentionReport

# (tool, config path relative to home, json key, label)
CHECKS: tuple[tuple[str, str, str, str], ...] = (
    ("claude-code", ".claude/settings.json", "cleanupPeriodDays",
     "transcript cleanup period (days)"),
    ("claude-desktop",
     "Library/Application Support/Claude/claude_desktop_config.json",
     "cleanupPeriodDays", "state cleanup period (days)"),
    ("cursor", "Library/Application Support/Cursor/User/settings.json",
     "cursor.chat.retentionDays", "chat retention (days)"),
)


def collect_retention(home: Optional[Path] = None) -> RetentionReport:
    """Does each tool have a documented lifecycle control configured?
    Static config reads only — no judgments about the values themselves."""
    home = home or Path.home()
    tools: list[RetentionEntry] = []
    for tool, rel, key, label in CHECKS:
        path = home / rel
        status, value = "absent", None
        try:
            if path.exists():
                data = json.loads(path.read_text())
                raw = data.get(key) if isinstance(data, dict) else None
                if isinstance(raw, (int, float)):
                    status, value = "configured", int(raw)
        except (json.JSONDecodeError, OSError):
            status = "absent"  # unreadable config ≈ no retention configured
        tools.append(RetentionEntry(tool=tool, setting=label,
                                    status=status, value=value))
    return RetentionReport(available=True, tools=tools)
