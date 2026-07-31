# Monitor Expansion Phase 2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Process-lifecycle depth (RSS-slope leak detection, fd counts, MCP fleet, churn), privacy/retention auditing (secrets scan, retention posture, launchd baseline), and work-loss protection (uncommitted/unpushed git work), plus an expanded categorized state-dir registry.

**Architecture:** Same patterns as Phase 1: pure `parse_*` + runner-injected `collect_*` collectors, additive models/config changes, new findings gated on availability, two new dashboard domains (`privacy`, `work`). Scan state files (churn/launchd baselines) live under `~/.local/share/ssdwtf/`.

**Tech Stack:** Python ≥3.10 stdlib only; stdlib `unittest`; spec `docs/superpowers/specs/2026-07-30-monitor-expansion.md` §10.

## Global Constraints

- Python standard library ONLY. No third-party imports. No sudo. Never `shell=True`; external commands only via `collectors._run.run_cmd`.
- Project root: `/Users/biscuit/wtfssd`. Branch: `phase-2`. Commit per task.
- Collectors never raise. Failures → `available=False`/`error` or empty structures + `note`.
- models.py changes are ADDITIVE ONLY (new dataclasses, new fields with defaults). All 141 existing tests must keep passing; the only sanctioned existing-test edits are stated explicitly in tasks (test_statedirs total semantics IF the nested-path rule changes its fixture's expectation; test_analyze domain set assertions are written against `analyze.DOMAINS` so they absorb the two new domains without edits).
- The secrets collector NEVER records, prints, or returns matched values — path, line number, and rule name only. It does nothing unless `secrets.enabled` is true.
- State-file collectors (churn, launchd) write ONLY their own JSON state file under `data_dir()` and only when collecting with the real default paths; tests inject temp paths.
- Run only your own test files from repo root. `from __future__ import annotations`, type hints, LF endings everywhere.

---

### Task 1: models.py + config.py Phase-2 extension

**Files:**
- Modify: `ssdwtf/models.py` (additive)
- Modify: `ssdwtf/config.py` (DEFAULTS additions + tier lists)
- Test: `tests/test_models.py` (append new class)

**Interfaces:**
- Produces: `ChurnReport`, `FdsReport`, `MCPServer`, `MCPReport`, `SecretMatch`, `SecretsReport`, `RetentionEntry`, `RetentionReport`, `LaunchdReport`, `SpotlightReport`, `LogsReport`, `RepoStatus`, `GitWatchReport`; `ProcessReport.ide_procs`; `StateDir.category`; `StateDirReport.category_totals`; `HealthReport` fields `churn, fds, mcp, secrets, retention, launchd, spotlight, logs, gitwatch`. Every later task imports these.

- [ ] **Step 1: Extend `ssdwtf/models.py`**

Add to `StateDir` (after `note`):

```python
    category: str = ""  # ai-state|ide-cache|build-artifacts|models|user-caches|dev-deps
```

Add to `StateDirReport` (after `note`):

```python
    category_totals: dict[str, int] = field(default_factory=dict)
```

Add to `ProcessReport` (after `note`):

```python
    ide_procs: list[GhostProcess] = field(default_factory=list)  # ALL IDE-family procs, any age
```

Append after `WriteRateReport`:

```python
@dataclass
class ChurnReport:
    available: bool
    error: Optional[str] = None
    pack_count: int = 0
    pack_bytes: int = 0
    added: int = 0
    removed: int = 0
    added_bytes: int = 0
    note: Optional[str] = None  # "baseline stored" on first run


@dataclass
class FdsReport:
    available: bool
    error: Optional[str] = None
    per_app: dict[str, int] = field(default_factory=dict)
    max_pid: int = 0
    max_name: str = ""
    max_count: int = 0


@dataclass
class MCPServer:
    name: str
    command: str
    live_pids: int = 0
    rss_mb: float = 0.0
    oldest_age_s: int = 0


@dataclass
class MCPReport:
    available: bool
    error: Optional[str] = None
    claude_running: bool = False
    servers: list[MCPServer] = field(default_factory=list)


@dataclass
class SecretMatch:
    path: str
    line: int
    rule: str


@dataclass
class SecretsReport:
    available: bool
    error: Optional[str] = None
    enabled: bool = False
    scanned_files: int = 0
    matches: list[SecretMatch] = field(default_factory=list)


@dataclass
class RetentionEntry:
    tool: str
    setting: str
    status: str                   # "configured" | "absent"
    value: Optional[int] = None


@dataclass
class RetentionReport:
    available: bool
    error: Optional[str] = None
    tools: list[RetentionEntry] = field(default_factory=list)


@dataclass
class LaunchdReport:
    available: bool
    error: Optional[str] = None
    agent_count: int = 0
    new_since_baseline: list[str] = field(default_factory=list)
    baseline_exists: bool = True


@dataclass
class SpotlightReport:
    available: bool
    error: Optional[str] = None
    indexing_enabled: Optional[bool] = None
    mds_cpu_pct: Optional[float] = None


@dataclass
class LogsReport:
    available: bool
    error: Optional[str] = None
    total_bytes: int = 0
    top: list[StateDir] = field(default_factory=list)


@dataclass
class RepoStatus:
    path: str
    error: Optional[str] = None
    uncommitted: int = 0
    untracked: int = 0
    has_remote: bool = True
    unpushed: int = 0


@dataclass
class GitWatchReport:
    available: bool
    error: Optional[str] = None
    repos: list[RepoStatus] = field(default_factory=list)
```

Extend `HealthReport` (after `external_smart`):

```python
    churn: ChurnReport = field(default_factory=lambda: ChurnReport(available=False))
    fds: FdsReport = field(default_factory=lambda: FdsReport(available=False))
    mcp: MCPReport = field(default_factory=lambda: MCPReport(available=False))
    secrets: SecretsReport = field(default_factory=lambda: SecretsReport(available=False))
    retention: RetentionReport = field(default_factory=lambda: RetentionReport(available=False))
    launchd: LaunchdReport = field(default_factory=lambda: LaunchdReport(available=False))
    spotlight: SpotlightReport = field(default_factory=lambda: SpotlightReport(available=False))
    logs: LogsReport = field(default_factory=lambda: LogsReport(available=False))
    gitwatch: GitWatchReport = field(default_factory=lambda: GitWatchReport(available=False))
```

Extend `report_from_dict`: inside it, extend the `_sub` usage with the new
reports, and handle the nested lists explicitly (mirror the ghosts pattern):

```python
    def _sub(cls, key):
        raw = d.get(key)
        if not raw:
            return cls(available=False)
        return cls(**{k: v for k, v in raw.items()
                      if k in cls.__dataclass_fields__})

    def _sublist(cls, item_cls, key, list_field):
        raw = d.get(key)
        if not raw:
            return cls(available=False)
        kwargs = {k: v for k, v in raw.items()
                  if k in cls.__dataclass_fields__ and k != list_field}
        kwargs[list_field] = [item_cls(**{k: v for k, v in item.items()
                                          if k in item_cls.__dataclass_fields__})
                              for item in raw.get(list_field, [])]
        return cls(**kwargs)
```

and in the return statement:

```python
        churn=_sub(ChurnReport, "churn"),
        fds=_sub(FdsReport, "fds"),
        mcp=_sublist(MCPReport, MCPServer, "mcp", "servers"),
        secrets=_sublist(SecretsReport, SecretMatch, "secrets", "matches"),
        retention=_sublist(RetentionReport, RetentionEntry, "retention", "tools"),
        launchd=_sub(LaunchdReport, "launchd"),
        spotlight=_sub(SpotlightReport, "spotlight"),
        logs=_sublist(LogsReport, StateDir, "logs", "top"),
        gitwatch=_sublist(GitWatchReport, RepoStatus, "gitwatch", "repos"),
```

(Replace the Phase-1 `_sub` with this pair — the `default_available`
parameter was already unused. Also extend the `statedirs` reconstruction:
`StateDir(**{k: v for k, v in s.items() if k in StateDir.__dataclass_fields__})`
and pass `category_totals=d["statedirs"].get("category_totals", {})`.)

- [ ] **Step 2: Extend `ssdwtf/config.py`**

Update `procs` and `tiers`, append new sections:

```python
    "procs": {"ghost_days": 3.0, "warn_count": 20,
              "leak_warn_mb_h": 100, "leak_window_h": 6},
```

```python
    "tiers": {"fast": ["smart", "swap", "disk", "processes", "pressure",
                       "system", "writerate", "retention", "launchd",
                       "spotlight", "mcp"],
              "slow": ["statedirs", "apfs", "backup", "crashes", "churn",
                       "fds", "secrets", "logs", "gitwatch"]},
```

```python
    "churn": {"warn_turnover": 20, "warn_gb": 5},
    "fds": {"warn_count": 4000},
    "mcp": {"config_path": "~/Library/Application Support/Claude/claude_desktop_config.json"},
    "secrets": {"enabled": False},
    "spotlight": {"warn_cpu_pct": 50},
    "logs": {"warn_gb_day": 0.5, "extra_dirs": []},
    "git": {"repos": [], "warn_changes": 50, "warn_unpushed": 10},
```

- [ ] **Step 3: Append to `tests/test_models.py`** (before the `__main__` block)

```python
class TestPhase2Models(unittest.TestCase):
    def test_new_reports_default_unavailable(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        for name in ("churn", "fds", "mcp", "secrets", "retention",
                     "launchd", "spotlight", "logs", "gitwatch"):
            self.assertFalse(getattr(rep, name).available, name)

    def test_statedir_category_and_totals_default(self):
        sd = models.StateDir(key="k", path="/x", exists=True, size_bytes=1)
        self.assertEqual(sd.category, "")
        self.assertEqual(models.StateDirReport().category_totals, {})

    def test_process_report_ide_procs_default(self):
        self.assertEqual(models.ProcessReport().ide_procs, [])

    def test_roundtrip_nested_phase2(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        rep.mcp = models.MCPReport(
            available=True, claude_running=True,
            servers=[models.MCPServer(name="firecrawl", command="node fc.js",
                                      live_pids=2, rss_mb=310.5)])
        rep.gitwatch = models.GitWatchReport(
            available=True,
            repos=[models.RepoStatus(path="/repo", uncommitted=3,
                                     has_remote=False, unpushed=7)])
        rep.secrets = models.SecretsReport(
            available=True, enabled=True,
            matches=[models.SecretMatch(path="/f", line=9, rule="aws-access-key")])
        back = models.report_from_dict(models.report_to_dict(rep))
        self.assertEqual(back.mcp.servers[0].name, "firecrawl")
        self.assertEqual(back.gitwatch.repos[0].unpushed, 7)
        self.assertEqual(back.secrets.matches[0].rule, "aws-access-key")

    def test_from_dict_tolerates_phase1_rows(self):
        rep = models.make_empty_report("2026-07-30T10:00:00", 64.0)
        d = models.report_to_dict(rep)
        for k in ("churn", "fds", "mcp", "secrets", "retention",
                  "launchd", "spotlight", "logs", "gitwatch"):
            d.pop(k, None)
        back = models.report_from_dict(d)
        self.assertFalse(back.mcp.available)
```

- [ ] **Step 4: Run tests** — `python3 -m unittest tests.test_models tests.test_config -v` → all pass
- [ ] **Step 5: Commit** — `git add ssdwtf/models.py ssdwtf/config.py tests/test_models.py && git commit -m "phase2: additive models+config extension (lifecycle/privacy/work reports)"`

---

### Task 2: statedirs registry expansion + categories + double-count guard

**Files:**
- Modify: `ssdwtf/collectors/statedirs.py`
- Test: `tests/test_statedirs.py` (extend; ONE sanctioned edit IF needed, see Step 3)

**Interfaces:**
- Consumes: Task 1 `StateDir.category`, `StateDirReport.category_totals`.
- Produces: 4-tuple `STATE_DIRS` entries `(key, rel_path, note, category)`; `collect_statedirs` fills category + category_totals; `total_bytes` excludes entries nested inside another tracked entry.

- [ ] **Step 1: Rewrite the `STATE_DIRS` tuple and `collect_statedirs` in `ssdwtf/collectors/statedirs.py`**

```python
# (key, path relative to home, note, category)
STATE_DIRS: tuple[tuple[str, str, str, str], ...] = (
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
    ("jetbrains-app-support", "Library/Application Support/JetBrains", "JetBrains IDE state", "ide-cache"),
    ("ollama-models", ".ollama", "Ollama models", "models"),
    ("lmstudio-cache", ".cache/lm-studio", "LM Studio models/cache", "models"),
    ("huggingface-cache", ".cache/huggingface", "Hugging Face hub cache", "models"),
    ("mlx-cache", ".cache/mlx", "MLX model cache", "models"),
    ("docker-data", "Library/Containers/com.docker.docker", "Docker Desktop VM data", "dev-deps"),
    ("xcode-deriveddata", "Library/Developer/Xcode/DerivedData", "Xcode build products", "build-artifacts"),
    ("user-caches", "Library/Caches", "User caches", "user-caches"),
)
```

In `collect_statedirs`, build each `StateDir` with `category=category`, then
compute totals with the double-count guard:

```python
    dirs: list[StateDir] = []
    for key, rel, note, category in STATE_DIRS:
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
```

- [ ] **Step 2: Extend `tests/test_statedirs.py`**

Append (before `__main__`), following the file's existing tmp-home pattern:

```python
    def test_categories_and_double_count_guard(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            app = home / "Library/Application Support/Cursor"
            (app / "User/globalStorage").mkdir(parents=True)
            (app / "blob.bin").write_bytes(b"x" * 1000)
            (app / "User/globalStorage/state.vscdb").write_bytes(b"y" * 500)
            rep = statedirs.collect_statedirs(home=home)
            by_key = {d.key: d for d in rep.dirs}
            self.assertEqual(by_key["cursor-app-support"].category, "ai-state")
            # total counts cursor-app-support (1500) but NOT cursor-vscdb
            # (nested) — no double count
            self.assertEqual(rep.total_bytes, 1500)
            self.assertEqual(rep.category_totals.get("ai-state"), 1500)
            # vscdb is still reported individually
            self.assertEqual(by_key["cursor-vscdb"].size_bytes, 500)
```

- [ ] **Step 3: Sanctioned edit IF needed** — run `python3 -m unittest tests.test_statedirs -v`. If the pre-existing test asserting `rep.total_bytes == sum(d.size_bytes for d in rep.dirs)` fails because its fixture builds nested entries, update that assertion to the double-count-safe expectation (sum of non-nested) with a comment. If it passes unmodified (flat fixture), leave it untouched. Record which happened in your report.
- [ ] **Step 4: Run tests** — `python3 -m unittest tests.test_statedirs -v` → all pass
- [ ] **Step 5: Commit** — `git add ssdwtf/collectors/statedirs.py tests/test_statedirs.py && git commit -m "phase2: statedirs registry expansion, categories, double-count guard"`

---

### Task 3: processes.py ide_procs extension (RSS slope feed)

**Files:**
- Modify: `ssdwtf/collectors/processes.py`
- Test: `tests/test_processes.py` (extend only)

**Interfaces:**
- Consumes: Task 1 `ProcessReport.ide_procs`.
- Produces: `parse_ps` fills `ide_procs` with every IDE-family process (any age), sorted by RSS desc. Task 13 reads it; Task 14 records `procs.rss.<pid>` metrics from it.

- [ ] **Step 1: Modify `parse_ps` in `ssdwtf/collectors/processes.py`**

```python
def parse_ps(text: str, ghost_seconds: int) -> ProcessReport:
    ghosts: list[GhostProcess] = []
    ide_procs: list[GhostProcess] = []
    total = 0
    for line in text.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        pid, ppid, etime, rss_kb, comm = parts
        if not is_ide_process(comm):
            continue
        total += 1
        proc = GhostProcess(
            pid=int(pid), ppid=int(ppid), name=comm.strip(),
            age_seconds=etime_to_seconds(etime), rss_mb=int(rss_kb) / 1024,
        )
        ide_procs.append(proc)
        if proc.age_seconds >= ghost_seconds:
            ghosts.append(proc)
    ghosts.sort(key=lambda g: g.age_seconds, reverse=True)
    ide_procs.sort(key=lambda g: g.rss_mb, reverse=True)
    return ProcessReport(ghosts=ghosts, total_ide_processes=total,
                         ide_procs=ide_procs)
```

(`collect_processes` is unchanged.)

- [ ] **Step 2: Extend `tests/test_processes.py`** — append (before `__main__`), using the file's existing ps fixture/helpers:

```python
    def test_ide_procs_all_ages_sorted_by_rss(self):
        text = (Path(__file__).parent / "fixtures" / "ps.txt").read_text()
        rep = processes.parse_ps(text, ghost_seconds=3 * 86400)
        self.assertGreaterEqual(len(rep.ide_procs), len(rep.ghosts))
        self.assertEqual(rep.total_ide_processes, len(rep.ide_procs))
        rss = [p.rss_mb for p in rep.ide_procs]
        self.assertEqual(rss, sorted(rss, reverse=True))
        # ghosts are a subset of ide_procs by pid
        self.assertTrue({g.pid for g in rep.ghosts} <=
                        {p.pid for p in rep.ide_procs})
```

(Add `from pathlib import Path` if the file lacks it.)
- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_processes -v` → all pass
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/processes.py tests/test_processes.py && git commit -m "phase2: processes ide_procs (all-ages RSS feed for slope detection)"`

---

### Task 4: Churn collector (snapshot turnover)

**Files:**
- Create: `ssdwtf/collectors/churn.py`
- Test: `tests/test_churn.py`

**Interfaces:**
- Consumes: `..models.ChurnReport`, `..config.data_dir`.
- Produces: `collect_churn(home=None, state_path=None) -> ChurnReport`. Task 13 reads `added`, `removed`, `pack_bytes`.

Design: watches `*.pack` under `~/.cursor` and `~/Library/Application Support/Cursor/CachedData`. Keeps `{relpath: size}` map in `<data_dir>/churn_state.json`. Turnover = |added| + |removed| since last collect. First run stores baseline (note set, zero turnover). Writes the state file ONLY when `state_path` is the default and `home` is the real home (tests inject both).

- [ ] **Step 1: Write `ssdwtf/collectors/churn.py`**

```python
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
                    if p.is_file():
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
    baseline_exists = state_path.exists()
    if baseline_exists:
        try:
            previous = json.loads(state_path.read_text()).get("packs", {})
        except (json.JSONDecodeError, OSError):
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
```

- [ ] **Step 2: Write `tests/test_churn.py`**

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ssdwtf.collectors import churn


def _mk(home: Path, rel: str, size: int) -> None:
    p = home / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)


class TestChurn(unittest.TestCase):
    def test_first_run_stores_baseline_zero_turnover(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            state = home / "state.json"
            _mk(home, ".cursor/idx/a.pack", 100)
            rep = churn.collect_churn(home=home, state_path=state)
            self.assertTrue(rep.available)
            self.assertEqual(rep.note, "baseline stored")
            self.assertEqual(rep.added, 0)
            self.assertEqual(rep.pack_count, 1)
            self.assertTrue(state.exists())

    def test_turnover_detected(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            state = home / "state.json"
            _mk(home, ".cursor/idx/a.pack", 100)
            churn.collect_churn(home=home, state_path=state)
            (home / ".cursor/idx/a.pack").unlink()
            _mk(home, ".cursor/idx/b.pack", 200)
            _mk(home, "Library/Application Support/Cursor/CachedData/c.pack", 50)
            rep = churn.collect_churn(home=home, state_path=state)
            self.assertEqual(rep.added, 2)
            self.assertEqual(rep.removed, 1)
            self.assertEqual(rep.pack_bytes, 250)

    def test_no_watch_dirs_is_clean_zero(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            rep = churn.collect_churn(home=home, state_path=home / "s.json")
            self.assertTrue(rep.available)
            self.assertEqual(rep.pack_count, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_churn -v` → 3 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/churn.py tests/test_churn.py && git commit -m "phase2: snapshot churn turnover collector"`

---

### Task 5: fd-count collector (lsof)

**Files:**
- Create: `ssdwtf/collectors/fds.py`
- Test: `tests/test_fds.py`

**Interfaces:**
- Consumes: `._run.run_cmd`, `..models.FdsReport`, `.processes.IDE_PATTERNS`.
- Produces: `parse_lsof(text) -> dict[int, tuple[str, int]]` (pid → (command, fd count)), `collect_fds(runner=run_cmd) -> FdsReport`.

- [ ] **Step 1: Write `ssdwtf/collectors/fds.py`**

```python
from __future__ import annotations

from typing import Callable, Optional

from ..models import FdsReport
from ._run import run_cmd
from .processes import IDE_PATTERNS


def parse_lsof(text: str) -> dict[int, tuple[str, int]]:
    """lsof -nP output → {pid: (command, open-fd count)}. Header skipped."""
    counts: dict[int, tuple[str, int]] = {}
    for line in text.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4 or not parts[1].isdigit():
            continue
        command, pid = parts[0], int(parts[1])
        name, n = counts.get(pid, (command, 0))
        counts[pid] = (name, n + 1)
    return counts


def _family(command: str) -> Optional[str]:
    low = command.lower()
    for pat in IDE_PATTERNS:
        if pat.strip("/. ") in low:
            return pat.strip("/. ")
    return None


def collect_fds(runner: Callable = run_cmd) -> FdsReport:
    """Open-fd counts per watched IDE family + the single worst pid.
    lsof is slow (~1-3 s) — this collector belongs to the slow tier."""
    out = runner(["lsof", "-nP"])
    if out is None:
        return FdsReport(available=False, error="lsof unavailable")
    per_pid = parse_lsof(out)
    per_app: dict[str, int] = {}
    max_pid, max_name, max_count = 0, "", 0
    for pid, (command, count) in per_pid.items():
        fam = _family(command)
        if fam is not None:
            per_app[fam] = per_app.get(fam, 0) + count
        if count > max_count:
            max_pid, max_name, max_count = pid, command, count
    return FdsReport(available=True, per_app=per_app,
                     max_pid=max_pid, max_name=max_name, max_count=max_count)
```

- [ ] **Step 2: Write `tests/test_fds.py`**

```python
from __future__ import annotations

import unittest

from ssdwtf.collectors import fds

LSOF = """COMMAND     PID  USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
Cursor     1001 biscuit cwd  DIR  1,4      640  123 /
Cursor     1001 biscuit txt  REG  1,4   123456  124 /a
Cursor     1001 biscuit  42u IPv4                  TCP *:80
Code       1002 biscuit cwd  DIR  1,4      640  125 /
sshd       1003 root    cwd  DIR  1,4      640  126 /
"""


class TestFds(unittest.TestCase):
    def test_parse_lsof(self):
        counts = fds.parse_lsof(LSOF)
        self.assertEqual(counts[1001], ("Cursor", 3))
        self.assertEqual(counts[1003], ("sshd", 1))

    def test_collect_aggregates_family_and_max(self):
        rep = fds.collect_fds(runner=lambda cmd: LSOF)
        self.assertTrue(rep.available)
        self.assertEqual(rep.per_app.get("cursor"), 3)
        self.assertEqual(rep.max_pid, 1001)
        self.assertEqual(rep.max_count, 3)
        self.assertNotIn("sshd", rep.per_app)

    def test_collect_degrades(self):
        rep = fds.collect_fds(runner=lambda cmd: None)
        self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_fds -v` → 3 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/fds.py tests/test_fds.py && git commit -m "phase2: lsof fd-count collector"`

---

### Task 6: MCP fleet collector

**Files:**
- Create: `ssdwtf/collectors/mcp.py`
- Test: `tests/test_mcp.py`

**Interfaces:**
- Consumes: `._run.run_cmd`, `..models.MCPReport/MCPServer`.
- Produces: `parse_mcp_config(text) -> dict[str, str]` (name → match string), `collect_mcp(config_path, runner=run_cmd, home=None) -> MCPReport`.

Design: one `ps -eo pid,etime,rss,args` call; a server is live when its
command basename appears in a process's args. `claude_running` = any args
containing `Claude.app/Contents/MacOS/Claude`. Orphans are derived in
analyze (server.live_pids > 0 while claude_running is False), not here.

- [ ] **Step 1: Write `ssdwtf/collectors/mcp.py`**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from ..models import MCPReport, MCPServer
from ._run import run_cmd
from .processes import etime_to_seconds

_CLAUDE_MARKER = "Claude.app/Contents/MacOS/Claude"


def parse_mcp_config(text: str) -> dict[str, str]:
    """claude_desktop_config.json → {server name: match string}. Tolerates
    missing/invalid config ({})."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return {}
    out: dict[str, str] = {}
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        command = str(spec.get("command", ""))
        args = " ".join(str(a) for a in spec.get("args", []))
        match = f"{command} {args}".strip()
        if match:
            out[str(name)] = match
    return out


def _basename(match: str) -> str:
    return match.split()[0].rsplit("/", 1)[-1]


def collect_mcp(config_path: Optional[Path] = None,
                runner: Callable = run_cmd,
                home: Optional[Path] = None) -> MCPReport:
    home = home or Path.home()
    config_path = config_path or (
        home / "Library/Application Support/Claude/claude_desktop_config.json")
    if not config_path.exists():
        return MCPReport(available=False,
                         error=f"no MCP config at {config_path}")
    try:
        declared = parse_mcp_config(config_path.read_text())
    except OSError as exc:
        return MCPReport(available=False, error=str(exc))

    ps = runner(["ps", "-eo", "pid,etime,rss,args"])
    if ps is None:
        return MCPReport(available=False, error="ps failed")

    procs: list[tuple[int, int, float, str]] = []  # pid, age_s, rss_mb, args
    claude_running = False
    for line in ps.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        pid_s, etime, rss_kb, args = parts
        if _CLAUDE_MARKER in args:
            claude_running = True
        try:
            procs.append((int(pid_s), etime_to_seconds(etime),
                          int(rss_kb) / 1024, args))
        except ValueError:
            continue

    servers: list[MCPServer] = []
    for name, match in sorted(declared.items()):
        token = _basename(match)
        hits = [p for p in procs if token and token in p[3]]
        servers.append(MCPServer(
            name=name, command=match,
            live_pids=len(hits),
            rss_mb=round(sum(p[2] for p in hits), 1),
            oldest_age_s=max((p[1] for p in hits), default=0),
        ))
    return MCPReport(available=True, claude_running=claude_running,
                     servers=servers)
```

- [ ] **Step 2: Write `tests/test_mcp.py`**

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ssdwtf.collectors import mcp

CONFIG = {"mcpServers": {
    "firecrawl": {"command": "node", "args": ["/opt/fc/dist/index.js"]},
    "x-api": {"command": "/usr/bin/python3", "args": ["server.py"]},
}}

PS = """  PID ELAPSED     RSS ARGS
  501 02:00:00  310272 node /opt/fc/dist/index.js
  502 5-00:00:00  10240 /usr/bin/python3 server.py
  503 01:00:00 9999999 /Applications/Claude.app/Contents/MacOS/Claude --flag
  504 00:30:00    5120 /usr/sbin/sshd
"""


class TestMcp(unittest.TestCase):
    def _config_file(self, td: str) -> Path:
        p = Path(td) / "cfg.json"
        p.write_text(json.dumps(CONFIG))
        return p

    def test_parse_config(self):
        got = mcp.parse_mcp_config(json.dumps(CONFIG))
        self.assertEqual(got["firecrawl"], "node /opt/fc/dist/index.js")
        self.assertEqual(mcp.parse_mcp_config("not json"), {})
        self.assertEqual(mcp.parse_mcp_config("{}"), {})

    def test_collect_live_servers(self):
        with tempfile.TemporaryDirectory() as td:
            rep = mcp.collect_mcp(config_path=self._config_file(td),
                                  runner=lambda cmd: PS, home=Path(td))
            self.assertTrue(rep.available)
            self.assertTrue(rep.claude_running)
            by_name = {s.name: s for s in rep.servers}
            self.assertEqual(by_name["firecrawl"].live_pids, 1)
            self.assertAlmostEqual(by_name["firecrawl"].rss_mb, 303.0, places=0)
            self.assertEqual(by_name["x-api"].oldest_age_s, 5 * 86400)

    def test_collect_missing_config_degrades(self):
        rep = mcp.collect_mcp(config_path=Path("/nonexistent-x.json"),
                              runner=lambda cmd: PS)
        self.assertFalse(rep.available)

    def test_collect_ps_failure_degrades(self):
        with tempfile.TemporaryDirectory() as td:
            rep = mcp.collect_mcp(config_path=self._config_file(td),
                                  runner=lambda cmd: None, home=Path(td))
            self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_mcp -v` → 4 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/mcp.py tests/test_mcp.py && git commit -m "phase2: MCP fleet collector"`

---

### Task 7: Secrets collector (opt-in, paths only)

**Files:**
- Create: `ssdwtf/collectors/secrets.py`
- Test: `tests/test_secrets.py`

**Interfaces:**
- Consumes: `..models.SecretsReport/SecretMatch`.
- Produces: `RULES: tuple[tuple[str, str], ...]`, `scan_text(path, text, rules, matches, cap)`, `collect_secrets(enabled, home=None) -> SecretsReport`.

Safety contract (review will verify): no code path returns, prints, logs, or
stores a matched secret value — only path, line number, rule name.

- [ ] **Step 1: Write `ssdwtf/collectors/secrets.py`**

```python
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
```

- [ ] **Step 2: Write `tests/test_secrets.py`**

```python
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from ssdwtf.collectors import secrets


class TestSecrets(unittest.TestCase):
    def test_disabled_is_inert(self):
        rep = secrets.collect_secrets(enabled=False, home=Path("/nope"))
        self.assertTrue(rep.available)
        self.assertFalse(rep.enabled)
        self.assertEqual(rep.matches, [])

    def test_scan_text_finds_rules_without_values(self):
        matches: list = []
        rules = tuple((n, __import__("re").compile(p)) for n, p in secrets.RULES)
        fake_aws = "AKIA" + "X" * 16  # built at runtime: no literal key in source
        secrets.scan_text("/f", '{"key": "' + fake_aws + '"}\nplain',
                          rules, matches)
        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual((m.path, m.line, m.rule), ("/f", 1, "aws-access-key"))
        self.assertNotIn(fake_aws, str(m))

    def test_collect_scans_claude_config(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cfg = home / "Library/Application Support/Claude/claude_desktop_config.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_text('{"mcpServers": {"x": {"env": '
                           '{"KEY": "ghp_aaaaaaaaaaaaaaaaaaaaaa"}}}}')
            rep = secrets.collect_secrets(enabled=True, home=home)
            self.assertTrue(rep.enabled)
            self.assertEqual(len(rep.matches), 1)
            self.assertEqual(rep.matches[0].rule, "github-token")

    def test_collect_scans_vscdb(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            db = home / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
            db.parent.mkdir(parents=True)
            conn = sqlite3.connect(str(db))
            conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
            conn.execute("INSERT INTO ItemTable VALUES ('k', ?)",
                         ("token = sk-ant-" + "a" * 30,))
            conn.commit(); conn.close()
            rep = secrets.collect_secrets(enabled=True, home=home)
            self.assertEqual(len(rep.matches), 1)
            self.assertEqual(rep.matches[0].rule, "anthropic-key")

    def test_oversized_files_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cfg = home / "Library/Application Support/Claude/claude_desktop_config.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_bytes(b'{"x": "' + b"AKIA" + b"X" * 16 + b'"}' + b" " * (6 * 1024 * 1024))
            rep = secrets.collect_secrets(enabled=True, home=home)
            self.assertEqual(rep.matches, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_secrets -v` → 5 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/secrets.py tests/test_secrets.py && git commit -m "phase2: opt-in secrets-at-rest scanner (paths/rules only)"`

---

### Task 8: Retention posture collector

**Files:**
- Create: `ssdwtf/collectors/retention.py`
- Test: `tests/test_retention.py`

**Interfaces:**
- Consumes: `..models.RetentionReport/RetentionEntry`.
- Produces: `CHECKS: tuple` (tool, path-rel, json key), `collect_retention(home=None) -> RetentionReport`.

- [ ] **Step 1: Write `ssdwtf/collectors/retention.py`**

```python
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
```

- [ ] **Step 2: Write `tests/test_retention.py`**

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ssdwtf.collectors import retention


class TestRetention(unittest.TestCase):
    def test_configured_and_absent(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cfg = home / ".claude/settings.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_text(json.dumps({"cleanupPeriodDays": 30}))
            rep = retention.collect_retention(home=home)
            self.assertTrue(rep.available)
            by_tool = {t.tool: t for t in rep.tools}
            self.assertEqual(by_tool["claude-code"].status, "configured")
            self.assertEqual(by_tool["claude-code"].value, 30)
            self.assertEqual(by_tool["cursor"].status, "absent")

    def test_invalid_json_counts_as_absent(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            cfg = home / ".claude/settings.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_text("{not json")
            rep = retention.collect_retention(home=home)
            self.assertEqual(rep.tools[0].status, "absent")

    def test_empty_home_all_absent(self):
        with tempfile.TemporaryDirectory() as td:
            rep = retention.collect_retention(home=Path(td))
            self.assertTrue(all(t.status == "absent" for t in rep.tools))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_retention -v` → 3 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/retention.py tests/test_retention.py && git commit -m "phase2: retention posture collector"`

---

### Task 9: launchd persistence audit

**Files:**
- Create: `ssdwtf/collectors/launchd.py`
- Test: `tests/test_launchd.py`

**Interfaces:**
- Consumes: `..models.LaunchdReport`, `..config.data_dir`.
- Produces: `collect_launchd(home=None, state_path=None, system_dirs=None) -> LaunchdReport`.

- [ ] **Step 1: Write `ssdwtf/collectors/launchd.py`**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..config import data_dir as default_data_dir
from ..models import LaunchdReport

_SYSTEM_DIRS = (Path("/Library/LaunchAgents"), Path("/Library/LaunchDaemons"))


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
```

- [ ] **Step 2: Write `tests/test_launchd.py`**

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ssdwtf.collectors import launchd


def _mk(d: Path, name: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("<plist/>")


class TestLaunchd(unittest.TestCase):
    def test_first_run_stores_baseline_no_findings(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            _mk(home / "Library/LaunchAgents", "com.a.plist")
            rep = launchd.collect_launchd(home=home,
                                          state_path=home / "b.json",
                                          system_dirs=())
            self.assertTrue(rep.available)
            self.assertFalse(rep.baseline_exists)
            self.assertEqual(rep.new_since_baseline, [])
            self.assertEqual(rep.agent_count, 1)

    def test_new_agent_detected_once(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            agents = home / "Library/LaunchAgents"
            _mk(agents, "com.a.plist")
            state = home / "b.json"
            launchd.collect_launchd(home=home, state_path=state, system_dirs=())
            _mk(agents, "com.evil.plist")
            rep = launchd.collect_launchd(home=home, state_path=state,
                                          system_dirs=())
            self.assertEqual(rep.new_since_baseline, ["com.evil.plist"])
            # baseline updated: second run sees nothing new
            rep2 = launchd.collect_launchd(home=home, state_path=state,
                                           system_dirs=())
            self.assertEqual(rep2.new_since_baseline, [])

    def test_system_dirs_included(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sysd = home / "sys"
            _mk(sysd, "com.sys.plist")
            rep = launchd.collect_launchd(home=home, state_path=home / "b.json",
                                          system_dirs=(sysd,))
            self.assertEqual(rep.agent_count, 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_launchd -v` → 3 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/launchd.py tests/test_launchd.py && git commit -m "phase2: launchd persistence baseline audit"`

---

### Task 10: Spotlight collector

**Files:**
- Create: `ssdwtf/collectors/spotlight.py`
- Test: `tests/test_spotlight.py`

**Interfaces:**
- Consumes: `._run.run_cmd`, `..models.SpotlightReport`.
- Produces: `parse_mdutil(text) -> Optional[bool]`, `parse_mds_cpu(ps_text) -> float`, `collect_spotlight(runner=run_cmd) -> SpotlightReport`.

- [ ] **Step 1: Write `ssdwtf/collectors/spotlight.py`**

```python
from __future__ import annotations

from typing import Callable, Optional

from ..models import SpotlightReport
from ._run import run_cmd

_MDS_NAMES = ("mds_stores", "mdworker")


def parse_mdutil(text: str) -> Optional[bool]:
    if "Indexing enabled" in text:
        return True
    if "Indexing disabled" in text:
        return False
    return None


def parse_mds_cpu(ps_text: str) -> float:
    """Sum %CPU of mds_stores/mdworker from `ps -eo pcpu,comm`."""
    total = 0.0
    for line in ps_text.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            cpu = float(parts[0])
        except ValueError:
            continue
        if any(name in parts[1] for name in _MDS_NAMES):
            total += cpu
    return total


def collect_spotlight(runner: Callable = run_cmd) -> SpotlightReport:
    md = runner(["mdutil", "-s", "/"])
    ps = runner(["ps", "-eo", "pcpu,comm"])
    if md is None and ps is None:
        return SpotlightReport(available=False, error="mdutil/ps unavailable")
    rep = SpotlightReport(available=True)
    if md is not None:
        rep.indexing_enabled = parse_mdutil(md)
    if ps is not None:
        rep.mds_cpu_pct = parse_mds_cpu(ps)
    return rep
```

- [ ] **Step 2: Write `tests/test_spotlight.py`**

```python
from __future__ import annotations

import unittest

from ssdwtf.collectors import spotlight

PS = """%CPU COMM
0.0 launchd
137.5 /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/Metadata.framework/Versions/A/Support/mds_stores
12.5 /System/.../mdworker
2.0 Cursor
"""


class TestSpotlight(unittest.TestCase):
    def test_parse_mdutil(self):
        self.assertTrue(spotlight.parse_mdutil("/:\n\tIndexing enabled. "))
        self.assertFalse(spotlight.parse_mdutil("/:\n\tIndexing disabled."))
        self.assertIsNone(spotlight.parse_mdutil("garbage"))

    def test_parse_mds_cpu(self):
        self.assertEqual(spotlight.parse_mds_cpu(PS), 150.0)

    def test_collect(self):
        def runner(cmd):
            return "/:\n\tIndexing enabled. " if "mdutil" in cmd else PS
        rep = spotlight.collect_spotlight(runner=runner)
        self.assertTrue(rep.available)
        self.assertTrue(rep.indexing_enabled)
        self.assertEqual(rep.mds_cpu_pct, 150.0)

    def test_collect_degrades(self):
        rep = spotlight.collect_spotlight(runner=lambda cmd: None)
        self.assertFalse(rep.available)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_spotlight -v` → 4 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/spotlight.py tests/test_spotlight.py && git commit -m "phase2: spotlight indexing collector"`

---

### Task 11: Logs collector

**Files:**
- Create: `ssdwtf/collectors/logs.py`
- Test: `tests/test_logs.py`

**Interfaces:**
- Consumes: `..models.LogsReport/StateDir`, `.statedirs.dir_size_bytes`.
- Produces: `collect_logs(home=None, extra_dirs=(), top_n=5) -> LogsReport`.

- [ ] **Step 1: Write `ssdwtf/collectors/logs.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..models import LogsReport, StateDir
from .statedirs import dir_size_bytes


def collect_logs(home: Optional[Path] = None,
                 extra_dirs: tuple[str, ...] = (),
                 top_n: int = 5) -> LogsReport:
    """Sizes ~/Library/Logs children + configured extra log dirs.
    Pure filesystem; never raises."""
    home = home or Path.home()
    roots: list[tuple[str, Path]] = []
    logs_root = home / "Library/Logs"
    try:
        if logs_root.is_dir():
            for child in sorted(logs_root.iterdir()):
                roots.append((f"logs/{child.name}", child))
    except OSError:
        pass
    for rel in extra_dirs:
        roots.append((rel, home / rel))

    entries: list[StateDir] = []
    total = 0
    for key, path in roots:
        try:
            if not path.exists():
                continue
            size = dir_size_bytes(path)
        except OSError:
            continue
        total += size
        entries.append(StateDir(key=key, path=str(path), exists=True,
                                size_bytes=size, category="logs"))
    entries.sort(key=lambda e: e.size_bytes, reverse=True)
    return LogsReport(available=True, total_bytes=total,
                      top=entries[:top_n])
```

- [ ] **Step 2: Write `tests/test_logs.py`**

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ssdwtf.collectors import logs


class TestLogs(unittest.TestCase):
    def test_sizes_and_top(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            big = home / "Library/Logs/Cursor"
            big.mkdir(parents=True)
            (big / "big.log").write_bytes(b"x" * 3000)
            small = home / "Library/Logs/Other"
            small.mkdir(parents=True)
            (small / "s.log").write_bytes(b"y" * 100)
            extra = home / "mcps/firecrawl"
            extra.mkdir(parents=True)
            (extra / "e.log").write_bytes(b"z" * 500)
            rep = logs.collect_logs(home=home, extra_dirs=("mcps/firecrawl",))
            self.assertTrue(rep.available)
            self.assertEqual(rep.total_bytes, 3600)
            self.assertEqual(rep.top[0].key, "logs/Cursor")
            self.assertIn("mcps/firecrawl", {e.key for e in rep.top})

    def test_missing_logs_dir_is_zero(self):
        with tempfile.TemporaryDirectory() as td:
            rep = logs.collect_logs(home=Path(td))
            self.assertTrue(rep.available)
            self.assertEqual(rep.total_bytes, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_logs -v` → 2 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/logs.py tests/test_logs.py && git commit -m "phase2: log growth collector"`

---

### Task 12: Git work-protection collector

**Files:**
- Create: `ssdwtf/collectors/gitwatch.py`
- Test: `tests/test_gitwatch.py`

**Interfaces:**
- Consumes: `._run.run_cmd`, `..models.GitWatchReport/RepoStatus`.
- Produces: `parse_status(text) -> tuple[int, int]` (uncommitted, untracked), `collect_repo(path, runner) -> RepoStatus`, `collect_gitwatch(repos, runner=run_cmd) -> GitWatchReport`. All git invocations are read-only (`status --porcelain`, `remote`, `log --branches --not --remotes --oneline`) — no fetch, no network.

- [ ] **Step 1: Write `ssdwtf/collectors/gitwatch.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from ..models import GitWatchReport, RepoStatus
from ._run import run_cmd


def parse_status(text: str) -> tuple[int, int]:
    """git status --porcelain → (uncommitted tracked changes, untracked files)."""
    uncommitted = untracked = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("??"):
            untracked += 1
        else:
            uncommitted += 1
    return uncommitted, untracked


def collect_repo(path: Path, runner: Callable = run_cmd) -> RepoStatus:
    if not (path / ".git").exists():
        return RepoStatus(path=str(path), error="not a git repository")
    status = runner(["git", "-C", str(path), "status", "--porcelain"])
    if status is None:
        return RepoStatus(path=str(path), error="git status failed")
    uncommitted, untracked = parse_status(status)
    remotes = runner(["git", "-C", str(path), "remote"])
    has_remote = bool(remotes and remotes.strip())
    unpushed = 0
    if has_remote:
        log = runner(["git", "-C", str(path), "log", "--branches",
                      "--not", "--remotes", "--oneline"])
        if log:
            unpushed = sum(1 for line in log.splitlines() if line.strip())
    return RepoStatus(path=str(path), uncommitted=uncommitted,
                      untracked=untracked, has_remote=has_remote,
                      unpushed=unpushed)


def collect_gitwatch(repos: list[str],
                     runner: Callable = run_cmd) -> GitWatchReport:
    """Read-only work-loss audit of configured repositories. Never fetches,
    never mutates, never raises."""
    return GitWatchReport(
        available=True,
        repos=[collect_repo(Path(r).expanduser(), runner) for r in repos])
```

- [ ] **Step 2: Write `tests/test_gitwatch.py`**

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ssdwtf.collectors import gitwatch


def _runner_for(status="", remotes="origin\n", log="abc123 work\n"):
    def runner(cmd):
        if "status" in cmd:
            return status
        if cmd[-1] == "remote" or "remote" in cmd and "log" not in cmd:
            return remotes
        if "log" in cmd:
            return log
        return ""
    return runner


class TestGitWatch(unittest.TestCase):
    def test_parse_status(self):
        self.assertEqual(gitwatch.parse_status(
            " M file.py\n?? new.txt\n?? other.txt\nA  added.py\n"), (2, 2))

    def test_collect_repo_full(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".git").mkdir()
            rep = gitwatch.collect_repo(Path(td), runner=_runner_for(
                status=" M a.py\n?? b.txt\n"))
            self.assertIsNone(rep.error)
            self.assertEqual((rep.uncommitted, rep.untracked), (1, 1))
            self.assertTrue(rep.has_remote)
            self.assertEqual(rep.unpushed, 1)

    def test_collect_repo_no_remote_skips_unpushed(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".git").mkdir()
            rep = gitwatch.collect_repo(Path(td), runner=_runner_for(
                remotes="", log=""))
            self.assertFalse(rep.has_remote)
            self.assertEqual(rep.unpushed, 0)

    def test_collect_repo_not_a_repo(self):
        with tempfile.TemporaryDirectory() as td:
            rep = gitwatch.collect_repo(Path(td), runner=_runner_for())
            self.assertEqual(rep.error, "not a git repository")

    def test_collect_gitwatch(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".git").mkdir()
            rep = gitwatch.collect_gitwatch([td], runner=_runner_for())
            self.assertTrue(rep.available)
            self.assertEqual(len(rep.repos), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_gitwatch -v` → 5 OK
- [ ] **Step 4: Commit** — `git add ssdwtf/collectors/gitwatch.py tests/test_gitwatch.py && git commit -m "phase2: read-only git work-protection collector"`

---

### Task 13: analyze.py — Phase-2 findings + 10 domains

**Files:**
- Modify: `ssdwtf/analyze.py`
- Test: `tests/test_analyze.py` (append new class)

**Interfaces:**
- Consumes: all Phase-2 collectors' reports + `metrics.rate_per_day`.
- Produces: `analyze(report, history, config, metrics_path=None)` (optional 4th param — back-compatible), new finding codes, `DOMAINS` grows to 10 with `privacy` and `work`.

- [ ] **Step 1: Modify `ssdwtf/analyze.py`**

Change the signature to:

```python
def analyze(report: HealthReport, history: list[HealthReport],
            config: dict, metrics_path=None) -> list[Finding]:
```

Add to imports: `from . import metrics` (module import, no circularity —
metrics imports only models/config).

Extend `DOMAINS` and `_DOMAIN_BY_PREFIX`:

```python
DOMAINS: tuple[str, ...] = ("drive", "backup", "headroom", "memory",
                            "processes", "state", "stability", "telemetry",
                            "privacy", "work")
```

```python
    "secrets.": "privacy", "retention.": "privacy",
    "work.": "work",
    "mcp.": "processes",
    "logs.": "state",
    "launchd.": "stability", "spotlight.": "stability",
```

Extend the `collector_ok` map in `domain_statuses`:

```python
        "privacy": report.secrets.available or report.retention.available,
        "work": report.gitwatch.available,
```

Append the new finding blocks at the end of `analyze` (before `return findings`):

```python
    # --- RSS leak slopes (derived from per-PID metrics history) ---
    cfg_procs2 = config.get("procs", {})
    if metrics_path is not None and report.processes.ide_procs:
        window_days = cfg_procs2.get("leak_window_h", 6) / 24.0
        threshold = cfg_procs2.get("leak_warn_mb_h", 100)
        leakers: list[tuple[str, int, float]] = []
        for proc in report.processes.ide_procs[:10]:
            rate = metrics.rate_per_day(f"procs.rss.{proc.pid}",
                                        days=window_days * 4,
                                        path=metrics_path)
            if rate is None:
                continue
            mb_per_h = rate / 24.0
            if mb_per_h >= threshold:
                leakers.append((proc.name, proc.pid, mb_per_h))
        if leakers:
            name, pid, slope = max(leakers, key=lambda t: t[2])
            findings.append(_f("monitor", "warn", "procs.leak",
                f"{len(leakers)} leaking process(es), worst: {name} +{slope:.0f} MB/h",
                f"pid {pid} keeps growing after its window should be idle — the 4.16 GB-per-closed-window pattern.",
                "Cmd+Q the owning app; if it returns, report it upstream.",
                evidence="derived"))

    # --- Snapshot churn ---
    ch = report.churn
    cfg_ch = config.get("churn", {})
    if ch.available and ch.note is None:
        turnover = ch.added + ch.removed
        size_burst = ch.added_bytes >= cfg_ch.get("warn_gb", 5) * 1e9
        if turnover >= cfg_ch.get("warn_turnover", 20) or size_burst:
            findings.append(_f("clean", "warn", "state.churn",
                f"Snapshot churn: +{ch.added} −{ch.removed} .pack files since last scan",
                f"{ch.pack_count} packs, {ch.pack_bytes / 1e9:.1f} GB now, +{ch.added_bytes / 1e9:.1f} GB new. Create-destroy churn is write volume that never shows as missing space.",
                "Constrain the indexer: `ssdwtf optimize ignore` in each project root."))

    # --- File descriptors ---
    fd = report.fds
    cfg_fd = config.get("fds", {})
    if fd.available:
        limit = cfg_fd.get("warn_count", 4000)
        worst = [(app, n) for app, n in fd.per_app.items() if n >= limit]
        if worst:
            app, n = max(worst, key=lambda t: t[1])
            findings.append(_f("monitor", "warn", "procs.fds",
                f"{app} holds {n} open file descriptors",
                f"Worst single pid: {fd.max_name} ({fd.max_pid}) with {fd.max_count}. fd exhaustion causes the mysterious mid-run crash.",
                "Restart the offending app; check for file-watcher loops."))

    # --- MCP fleet ---
    mc = report.mcp
    if mc.available:
        orphans = [s for s in mc.servers
                   if s.live_pids > 0 and not mc.claude_running]
        if orphans:
            names = ", ".join(s.name for s in orphans[:5])
            findings.append(_f("monitor", "warn", "mcp.orphan",
                f"{len(orphans)} MCP server(s) alive but Claude is not running: {names}",
                "Orphaned stdio servers are structurally the same leak as ghost IDE helpers.",
                "Kill the pids or restart Claude so it reaps them."))
        elif mc.claude_running:
            dead = [s for s in mc.servers if s.live_pids == 0]
            if dead:
                findings.append(_f("monitor", "info", "mcp.dead",
                    f"{len(dead)} configured MCP server(s) have no live process",
                    ", ".join(s.name for s in dead[:5]),
                    "Check Claude Desktop's MCP logs if you expected them."))

    # --- Secrets (opt-in) ---
    se = report.secrets
    if se.available and se.enabled and se.matches:
        by_rule: dict[str, int] = {}
        for m in se.matches:
            by_rule[m.rule] = by_rule.get(m.rule, 0) + 1
        top = ", ".join(f"{r}×{n}" for r, n in
                        sorted(by_rule.items(), key=lambda t: -t[1])[:3])
        findings.append(_f("monitor", "warn", "secrets.exposed",
            f"{len(se.matches)} credential pattern(s) at rest in agent state ({top})",
            f"Example location: {se.matches[0].path}:{se.matches[0].line}. Values are never displayed or stored by ssdwtf.",
            "Rotate the exposed keys; move secrets to env vars or a manager."))

    # --- Retention posture ---
    rt = report.retention
    if rt.available:
        missing = [t.tool for t in rt.tools if t.status == "absent"]
        if missing:
            findings.append(_f("optimize", "info", "retention.missing",
                f"No retention/cleanup setting found for: {', '.join(missing)}",
                "Tools without lifecycle controls accumulate unbounded state.",
                "Set cleanupPeriodDays where supported; audit the rest monthly."))

    # --- launchd persistence ---
    ld = report.launchd
    if ld.available and ld.new_since_baseline:
        findings.append(_f("monitor", "warn", "launchd.new",
            f"{len(ld.new_since_baseline)} new LaunchAgent/Daemon(s) installed",
            ", ".join(ld.new_since_baseline[:5]) + " — ghosts that survive Cmd+Q usually survive because something relaunches them.",
            "Inspect: `launchctl list | grep <name>`; remove if unwanted."))

    # --- Spotlight ---
    sp = report.spotlight
    cfg_sp = config.get("spotlight", {})
    if (sp.available and sp.mds_cpu_pct is not None
            and sp.mds_cpu_pct >= cfg_sp.get("warn_cpu_pct", 50)):
        findings.append(_f("monitor", "warn", "spotlight.storm",
            f"Spotlight indexing at {sp.mds_cpu_pct:.0f}% CPU",
            "Agents creating thousands of files trigger mds reindexing storms — a distinct write/CPU source.",
            "Consider Spotlight privacy exclusions for agent workspace dirs."))

    # --- Log growth (derived) ---
    cfg_logs = config.get("logs", {})
    if metrics_path is not None and report.logs.available:
        rate = metrics.rate_per_day("logs.total_gb",
                                    days=7, path=metrics_path)
        if rate is not None and rate >= cfg_logs.get("warn_gb_day", 0.5):
            findings.append(_f("clean", "warn", "logs.growth",
                f"Logs growing ~{rate:.1f} GB/day",
                "Verbose MCP servers and unified logging quietly write gigabytes.",
                "Check the top log dirs in the scan; quiet the noisiest tool.",
                evidence="derived"))

    # --- Work-loss protection ---
    gw = report.gitwatch
    cfg_git = config.get("git", {})
    if gw.available:
        no_remote = [r for r in gw.repos if r.error is None and not r.has_remote]
        if no_remote:
            findings.append(_f("monitor", "warn", "work.no_remote",
                f"{len(no_remote)} repo(s) have no remote configured",
                ", ".join(r.path for r in no_remote[:3]) + " — no off-machine copy exists.",
                "Add a remote and push, or confirm the repo is covered by backup."))
        dirty = [r for r in gw.repos if r.error is None
                 and r.uncommitted + r.untracked >= cfg_git.get("warn_changes", 50)]
        if dirty:
            r = max(dirty, key=lambda r: r.uncommitted + r.untracked)
            findings.append(_f("monitor", "warn", "work.uncommitted",
                f"{r.path}: {r.uncommitted} changed + {r.untracked} untracked files",
                "Large uncommitted work is one agent mistake away from loss.",
                "Commit or stash; ssdwtf will never push for you."))
        unpushed = [r for r in gw.repos if r.error is None
                    and r.unpushed >= cfg_git.get("warn_unpushed", 10)]
        if unpushed:
            r = max(unpushed, key=lambda r: r.unpushed)
            findings.append(_f("monitor", "warn", "work.unpushed",
                f"{r.path}: {r.unpushed} commits not on any remote",
                "Local-only commits are single-point-of-failure work.",
                "Push when ready; ssdwtf only reports."))
```

- [ ] **Step 2: Append to `tests/test_analyze.py`** (before `__main__`)

```python
class TestPhase2Findings(unittest.TestCase):
    def _analyze(self, rep, cfg=None, metrics_path=None):
        return analyze.analyze(rep, [], cfg or dict(DEFAULTS),
                               metrics_path=metrics_path)

    def test_churn_finding(self):
        rep = _base_report()
        rep.churn = models.ChurnReport(available=True, added=15, removed=10,
                                       pack_count=100, pack_bytes=int(2e9))
        self.assertIn("state.churn",
                      {f.code for f in self._analyze(rep)})

    def test_churn_quiet_on_baseline_run(self):
        rep = _base_report()
        rep.churn = models.ChurnReport(available=True, added=0, removed=0,
                                       note="baseline stored")
        self.assertNotIn("state.churn",
                         {f.code for f in self._analyze(rep)})

    def test_fds_finding(self):
        rep = _base_report()
        rep.fds = models.FdsReport(available=True,
                                   per_app={"cursor": 5000},
                                   max_pid=1, max_name="Cursor", max_count=5000)
        self.assertIn("procs.fds", {f.code for f in self._analyze(rep)})

    def test_mcp_orphan_and_dead(self):
        rep = _base_report()
        rep.mcp = models.MCPReport(
            available=True, claude_running=False,
            servers=[models.MCPServer(name="fc", command="node x",
                                      live_pids=1)])
        self.assertIn("mcp.orphan", {f.code for f in self._analyze(rep)})
        rep.mcp = models.MCPReport(
            available=True, claude_running=True,
            servers=[models.MCPServer(name="fc", command="node x",
                                      live_pids=0)])
        self.assertIn("mcp.dead", {f.code for f in self._analyze(rep)})

    def test_secrets_never_without_enable(self):
        rep = _base_report()
        rep.secrets = models.SecretsReport(
            available=True, enabled=False,
            matches=[models.SecretMatch(path="/f", line=1, rule="x")])
        self.assertNotIn("secrets.exposed",
                         {f.code for f in self._analyze(rep)})
        rep.secrets = models.SecretsReport(
            available=True, enabled=True,
            matches=[models.SecretMatch(path="/f", line=1, rule="aws-access-key")])
        self.assertIn("secrets.exposed",
                      {f.code for f in self._analyze(rep)})

    def test_retention_launchd_spotlight(self):
        rep = _base_report()
        rep.retention = models.RetentionReport(
            available=True,
            tools=[models.RetentionEntry(tool="cursor", setting="x",
                                         status="absent")])
        rep.launchd = models.LaunchdReport(
            available=True, new_since_baseline=["com.evil.plist"])
        rep.spotlight = models.SpotlightReport(available=True,
                                               mds_cpu_pct=137.5)
        codes = {f.code for f in self._analyze(rep)}
        self.assertIn("retention.missing", codes)
        self.assertIn("launchd.new", codes)
        self.assertIn("spotlight.storm", codes)

    def test_work_findings(self):
        rep = _base_report()
        rep.gitwatch = models.GitWatchReport(available=True, repos=[
            models.RepoStatus(path="/a", has_remote=False),
            models.RepoStatus(path="/b", uncommitted=40, untracked=20,
                              unpushed=15),
        ])
        codes = {f.code for f in self._analyze(rep)}
        self.assertIn("work.no_remote", codes)
        self.assertIn("work.uncommitted", codes)
        self.assertIn("work.unpushed", codes)

    def test_domains_now_ten(self):
        rep = _base_report()
        findings = self._analyze(rep)
        dom = analyze.domain_statuses(findings, rep)
        self.assertEqual(len(dom), 10)
        self.assertIn("privacy", dom)
        self.assertIn("work", dom)

    def test_procs_leak_with_metrics(self):
        import tempfile
        from pathlib import Path as P
        from ssdwtf import metrics as metrics_mod
        rep = _base_report()
        rep.processes = models.ProcessReport(ide_procs=[
            models.GhostProcess(pid=42, ppid=1, name="Cursor Helper",
                                age_seconds=100000, rss_mb=9000.0)])
        with tempfile.TemporaryDirectory() as td:
            db = P(td) / "m.db"
            # fabricate a rising RSS series: +4.8 GB/day = 200 MB/h
            for i, ts in enumerate(["2026-07-27T00:00:00",
                                    "2026-07-28T00:00:00",
                                    "2026-07-29T00:00:00"]):
                r = models.make_empty_report(ts, 64.0)
                r.processes = models.ProcessReport(ide_procs=[
                    models.GhostProcess(pid=42, ppid=1, name="Cursor Helper",
                                        age_seconds=1,
                                        rss_mb=1000.0 * (i + 1) + 800.0 * i)])
                metrics_mod.record(r, path=db)
            codes = {f.code for f in self._analyze(rep, metrics_path=db)}
            self.assertIn("procs.leak", codes)
            ev = [f for f in self._analyze(rep, metrics_path=db)
                  if f.code == "procs.leak"]
            self.assertEqual(ev[0].evidence, "derived")
```

- [ ] **Step 3: Run tests** — `python3 -m unittest tests.test_analyze -v` → all pass
- [ ] **Step 4: Commit** — `git add ssdwtf/analyze.py tests/test_analyze.py && git commit -m "phase2: lifecycle/privacy/work findings + 10 domains"`

---

### Task 14: cli.py wiring + metrics._extract Phase-2

**Files:**
- Modify: `ssdwtf/cli.py`, `ssdwtf/metrics.py`
- Test: `tests/test_cli.py`, `tests/test_metrics.py` (extend only)

**Interfaces:**
- Consumes: everything above.
- Produces: `build_report` collects all Phase-2 collectors with tier gating; `_run_scan` passes `metrics_path` to analyze; `_extract` records new metrics including dynamic `procs.rss.<pid>`.

- [ ] **Step 1: Extend `ssdwtf/metrics.py` `_extract`** — append before `return out`:

```python
    churn = getattr(report, "churn", None)
    if churn is not None and getattr(churn, "available", False) \
            and getattr(churn, "error", None) is None:
        put("churn.turnover", churn.added + churn.removed)
    fds = getattr(report, "fds", None)
    if fds is not None and getattr(fds, "available", False):
        put("fds.max_count", fds.max_count)
    mcp = getattr(report, "mcp", None)
    if mcp is not None and getattr(mcp, "available", False):
        put("mcp.live_servers", sum(1 for s in mcp.servers if s.live_pids > 0))
    logs = getattr(report, "logs", None)
    if logs is not None and getattr(logs, "available", False):
        put("logs.total_gb", logs.total_bytes / _GB)
    spot = getattr(report, "spotlight", None)
    if spot is not None and getattr(spot, "available", False):
        put("spotlight.mds_cpu_pct", spot.mds_cpu_pct)
    # per-PID RSS series feed the leak-slope detector (dynamic metric names)
    for proc in getattr(report.processes, "ide_procs", [])[:25]:
        put(f"procs.rss.{proc.pid}", proc.rss_mb)
```

- [ ] **Step 2: Wire `ssdwtf/cli.py`**

Add imports: `churn as churn_col`, `fds as fds_col`, `mcp as mcp_col`,
`secrets as secrets_col`, `retention as retention_col`,
`launchd as launchd_col`, `spotlight as spotlight_col`,
`logs as logs_col`, `gitwatch as gitwatch_col` from `.collectors`, and the
new report classes from `.models`.

In `build_report`, add to the `HealthReport(...)` call (fast tier:
retention/launchd/spotlight/mcp; slow tier: churn/fds/secrets/logs/gitwatch —
use the same `want()` helper; disabled secrets is not a tier skip):

```python
        retention=retention_col.collect_retention(),
        launchd=launchd_col.collect_launchd(),
        spotlight=spotlight_col.collect_spotlight(),
        mcp=mcp_col.collect_mcp(),
        churn=(churn_col.collect_churn() if want("churn")
               else ChurnReport(available=False, error="not collected (--fast)")),
        fds=(fds_col.collect_fds() if want("fds")
             else FdsReport(available=False, error="not collected (--fast)")),
        secrets=(secrets_col.collect_secrets(
                    enabled=config.get("secrets", {}).get("enabled", False))
                 if want("secrets")
                 else SecretsReport(available=False, error="not collected (--fast)")),
        logs=(logs_col.collect_logs(
                extra_dirs=tuple(config.get("logs", {}).get("extra_dirs", [])))
              if want("logs")
              else LogsReport(available=False, error="not collected (--fast)")),
        gitwatch=(gitwatch_col.collect_gitwatch(
                    config.get("git", {}).get("repos", []))
                  if want("gitwatch")
                  else GitWatchReport(available=False, error="not collected (--fast)")),
```

In `_run_scan`, pass the metrics path to analyze:

```python
    findings = analyze.analyze(rep, hist, config,
                               metrics_path=metrics.db_path() if use_history else None)
```

- [ ] **Step 3: Extend tests**

`tests/test_metrics.py` — append:

```python
    def test_phase2_metrics_extract(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "m.db"
            rep = _report("2026-07-30T10:00:00", 512.0)
            rep.churn = models.ChurnReport(available=True, added=3, removed=2)
            rep.logs = models.LogsReport(available=True,
                                         total_bytes=int(2.5e9))
            rep.processes = models.ProcessReport(ide_procs=[
                models.GhostProcess(pid=7, ppid=1, name="Cursor",
                                    age_seconds=10, rss_mb=512.0)])
            metrics.record(rep, path=db)
            self.assertEqual(metrics.latest("churn.turnover", path=db), 5.0)
            self.assertEqual(metrics.latest("logs.total_gb", path=db), 2.5)
            self.assertEqual(metrics.latest("procs.rss.7", path=db), 512.0)
```

(`models` import: add `from ssdwtf import models` if absent.)

`tests/test_cli.py` — extend the existing `--fast` test's not-called set to
include `churn_col`, `fds_col`, `secrets_col`, `logs_col`, `gitwatch_col`
mocks; add mock patches for the new fast-tier collectors
(`retention_col.collect_retention`, `launchd_col.collect_launchd`,
`spotlight_col.collect_spotlight`, `mcp_col.collect_mcp`) returning their
unavailable report defaults so the fast path stays hermetic. Follow the
file's existing pattern.

- [ ] **Step 4: Run tests** — `python3 -m unittest tests.test_cli tests.test_metrics -v` → all pass; then full suite `python3 -m unittest discover -s tests 2>&1 | tail -3` → all OK (record count); then live: `python3 -m ssdwtf scan --fast` (exit 0/1/2, no traceback, new fast collectors visible), `python3 -m ssdwtf scan --json | python3 -m json.tool >/dev/null && echo ok`, and one full `python3 -m ssdwtf scan` (confirm the new domains `privacy`/`work` appear in the domain table).
- [ ] **Step 5: Commit** — `git add ssdwtf/cli.py ssdwtf/metrics.py tests/test_cli.py tests/test_metrics.py && git commit -m "phase2: cli wiring for lifecycle/privacy/work collectors + metrics extraction"`

---

### Task 15: Docs sync + full verification

**Files:**
- Modify: `README.md`, `AGENTS.md`, `WIP.md` (gitignored, but update it)

- [ ] **Step 1: README.md** — in the existing structure, add: the ten domains; new monitored signals (RSS leak slopes, fd counts, MCP fleet, snapshot churn, secrets scan — explicitly OPT-IN, retention posture, launchd baseline, Spotlight, log growth, git work protection); new config keys; note `secrets.enabled` defaults to false and never displays values.
- [ ] **Step 2: AGENTS.md** — code-organization block: 10 new collector files; config keys; safety-model addition: secrets scanner is opt-in and never records values; churn/launchd state files under `~/.local/share/ssdwtf/`; test count updated from your verification run; tiers updated.
- [ ] **Step 3: WIP.md** — move Phase 2 items from Next to Done; refresh Current state (branch, test count).
- [ ] **Step 4: Full verification (from repo root)**

```sh
python3 -m unittest discover -s tests 2>&1 | tail -3
python3 -m ssdwtf scan --json | python3 -m json.tool > /dev/null && echo "json ok"
python3 -m ssdwtf scan --fast; echo "fast exit: $?"
python3 -m ssdwtf scan; echo "exit: $?"
python3 -m ssdwtf history | tail -3
```

Domain table must show 10 domains; `privacy` shows ok or unknown (secrets
disabled by default is ok), `work` shows unknown when `git.repos` is empty
(gitwatch available with zero repos → ok; either is acceptable, record which).
- [ ] **Step 5: Commit** — `git add README.md AGENTS.md && git commit -m "phase2: docs sync (README, AGENTS)"` (WIP.md is gitignored — do not stage it)

---

## Self-Review Notes (already applied)

- RSS slope uses `rate_per_day(days=leak_window_h/24 * 4)` — a wider sample
  window than the alert window, because rate_per_day needs ≥2 points and
  hourly fast scans take time to accumulate; the slope is in MB/day ÷ 24.
- MCP orphan detection lives in analyze (not the collector) so the collector
  stays a pure measurement.
- secrets scanning of state.vscdb uses sqlite read-only URI and caps rows;
  a locked DB degrades silently by design.
- gitwatch never fetches: unpushed counts use local refs only, so a stale
  remote ref means the count is a lower bound — documented behavior.
