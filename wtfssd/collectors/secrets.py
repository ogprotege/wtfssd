from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Optional

from ..models import SecretMatch, SecretsReport

RULES: tuple[tuple[str, str], ...] = (
    ("aws-access-key", r"AKIA[0-9A-Z]{16}"),
    ("anthropic-key", r"sk-ant-[A-Za-z0-9_-]{20,}"),
    ("openai-key", r"sk-[A-Za-z0-9]{32,}"),
    ("github-token", r"gh[pousr]_[A-Za-z0-9]{20,}"),
    ("private-key", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ("bearer-token", r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}"),
)

_MAX_FILE = 5 * 1024 * 1024
_MAX_MATCHES = 100
_VSCDB_ROWS = 500


def scan_text(path: str, text: str,
              rules: tuple[tuple[str, re.Pattern], ...],
              matches: list[SecretMatch]) -> None:
    for lineno, line in enumerate(text.splitlines(), 1):
        for rule_name, rx in rules:
            if rx.search(line):
                matches.append(SecretMatch(path=path, line=lineno,
                                           rule=rule_name))
                if len(matches) >= _MAX_MATCHES:
                    return


def _scan_file(path: Path, rules, matches: list[SecretMatch]) -> bool:
    try:
        if path.stat().st_size > _MAX_FILE:
            return False
        text = path.read_text(errors="replace")
    except OSError:
        return False
    scan_text(str(path), text, rules, matches)
    return True


def _scan_vscdb(path: Path, rules, matches: list[SecretMatch]) -> None:
    """state.vscdb ItemTable values, read-only, capped rows."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            cur = conn.execute(
                "SELECT value FROM ItemTable WHERE typeof(value) = 'text' "
                "LIMIT ?", (_VSCDB_ROWS,))
            for (value,) in cur.fetchall():
                scan_text(str(path), value, rules, matches)
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return  # locked/missing DB is not a scanner failure


def collect_secrets(enabled: bool, home: Optional[Path] = None) -> SecretsReport:
    """Opt-in credential-at-rest scan. Disabled → available but inert."""
    if not enabled:
        return SecretsReport(available=True, enabled=False)
    home = home or Path.home()
    rules = tuple((name, re.compile(pat)) for name, pat in RULES)
    matches: list[SecretMatch] = []
    scanned = 0

    targets: list[Path] = []
    claude_cfg = home / "Library/Application Support/Claude/claude_desktop_config.json"
    if claude_cfg.exists():
        targets.append(claude_cfg)
    projects = home / ".claude/projects"
    if projects.is_dir():
        try:
            targets.extend(sorted(projects.rglob("*.jsonl"))[:50])
        except OSError:
            pass
    for path in targets:
        if _scan_file(path, rules, matches):
            scanned += 1
        if len(matches) >= _MAX_MATCHES:
            break
    vscdb = home / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
    if vscdb.exists() and len(matches) < _MAX_MATCHES:
        _scan_vscdb(vscdb, rules, matches)
        scanned += 1

    return SecretsReport(available=True, enabled=True,
                         scanned_files=scanned, matches=matches)
