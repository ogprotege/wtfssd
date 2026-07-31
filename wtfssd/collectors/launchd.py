from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..config import data_dir as default_data_dir
from ..models import LaunchdReport

_SYSTEM_DIRS = (Path("/Library/LaunchAgents"), Path("/Library/LaunchDaemons"))
# The tool's own LaunchAgents (installed by `optimize install-agent`) must
# never be reported as new — wtfssd does not alert on itself.
_SELF_PREFIX = "com.wtfssd."


def collect_launchd(home: Optional[Path] = None,
                    state_path: Optional[Path] = None,
                    system_dirs: Optional[tuple[Path, ...]] = None
                    ) -> LaunchdReport:
    """New LaunchAgents/Daemons vs stored baseline. First run stores the
    baseline and reports nothing (baseline_exists=False). Never raises."""
    home = home or Path.home()
    state_path = state_path or (default_data_dir() / "launchd_baseline.json")
    dirs = system_dirs if system_dirs is not None else _SYSTEM_DIRS
    names: set[str] = set()
    for d in (home / "Library/LaunchAgents", *dirs):
        try:
            if d.is_dir():
                names.update(p.name for p in d.iterdir()
                             if p.name.endswith(".plist"))
        except OSError:
            continue
    names = {n for n in names if not n.startswith(_SELF_PREFIX)}

    baseline_exists = state_path.exists()
    previous: set[str] = set()
    if baseline_exists:
        try:
            previous = set(json.loads(state_path.read_text()).get("names", []))
        except (json.JSONDecodeError, OSError):
            previous = set()

    new = sorted(names - previous) if baseline_exists else []
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"names": sorted(names)}))
    except OSError:
        pass
    return LaunchdReport(available=True, agent_count=len(names),
                         new_since_baseline=new,
                         baseline_exists=baseline_exists)
