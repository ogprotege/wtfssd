# wtfssd — Design Spec

Date: 2026-07-30
Source article: `IDEA-SSD.txt` — "My MacBook Aged Three Years in Three Months of Vibe Coding"

## 1. Purpose

The article's thesis: agentic IDEs (Cursor, Claude Code, etc.) don't kill Apple Silicon SSDs —
they drown them in **unbounded local state**: runaway swap, ghost helper processes, gigabyte
chat databases, churning snapshot files, and evaporating free-space headroom. The drive's own
SMART accounting is the only honest wear signal, and it almost always says "healthy".

`wtfssd` is a macOS tool that operationalizes the article's "What I changed" section. It has
four pillars:

- **Monitor** — SMART wear, swap, free headroom, ghost IDE processes, state-directory sizes
  and growth rates, estimated write volume per day.
- **Alert** — threshold crossings (warn/critical) via macOS Notification Center, with cooldown
  so alerts don't spam.
- **Clean** — safe, dry-run-by-default cleanup of regenerable state (IDE caches/logs, chat-DB
  backups, Xcode DerivedData, large caches, stale `node_modules`), moving to Trash rather than
  deleting, with a backup-first rule for databases.
- **Optimize** — attack churn at the source: `.cursorignore`/indexer-ignore generation, headroom
  floor tracking, launchd agent for scheduled monitoring, monthly SMART habit.

Non-goals (v1): GUI/menu-bar app, Docker cleanup, remote/fleet monitoring, Windows/Linux support,
deleting anything under user project folders other than explicitly stale `node_modules`.

## 2. Technology & Constraints

- Python 3, **standard library only** (verified: Python 3.14.6 on macOS 26.6 arm64).
  No pip installs, no venv required.
- External commands used (all read-only): `smartctl` (optional; present on this machine and
  works without sudo), `sysctl`, `df`, `ps`, `du`, `osascript` (notifications).
- Every external dependency degrades gracefully: missing `smartctl` produces a "install
  smartmontools" note, not a crash.
- Runnable as `python3 -m wtfssd` from the repo, or installed via `pipx/pip install .`
  exposing a `wtfssd` console script.

## 3. Architecture

```
wtfssd/
  pyproject.toml
  README.md
  wtfssd/
    __init__.py            # version
    __main__.py            # entry: from .cli import main; main()
    cli.py                 # argparse: scan | clean | watch | optimize | history | config
    models.py              # dataclasses shared across all modules (the contract)
    config.py              # load/merge ~/.config/wtfssd/config.json over defaults
    collectors/
      __init__.py
      _run.py              # run_cmd(): subprocess wrapper (timeout, no shell, text, never raises)
      smart.py             # smartctl -a /dev/disk0 → SmartReport
      swap.py              # sysctl vm.swapusage → SwapReport
      disk.py              # df -k /System/Volumes/Data → DiskReport
      processes.py         # ps -eo pid,ppid,etime,rss,comm → ghost IDE helpers → ProcessReport
      statedirs.py         # known state dirs, state.vscdb, *.pack counts/sizes → StateDirReport
    analyze.py             # reports + config + history → list[Finding] + health score 0–100
    history.py             # JSONL append/read at ~/.local/share/wtfssd/history.jsonl; trends
    alerts.py              # Finding → osascript notification; cooldown state file
    cleaners.py            # CleanupTarget registry + dry-run/apply engine (Trash, guards)
    optimize.py            # .cursorignore writer, LaunchAgent plist install/uninstall
    report.py              # human tables and --json serialization of HealthReport/Findings
  tests/
    fixtures/              # captured outputs: smartctl.txt, sysctl_swap.txt, df.txt, ps.txt
    test_smart.py test_swap.py test_disk.py test_processes.py test_statedirs.py
    test_analyze.py test_history.py test_alerts.py test_cleaners.py test_optimize.py
    test_cli.py test_report.py test_config.py
```

Data flow:

```
collectors ──► models.HealthReport ──► analyze ──► [Finding] + score ──► report (text|json)
                                     │                    │
                                     └─► history.append   └─► alerts.notify (watch mode)
cleaners:  collectors(statedirs/disk) ──► size targets ──► dry-run print | --apply → Trash
optimize:  config ──► write ignore files / LaunchAgent plist
```

### Module contracts (models.py — the fixed interface)

```python
@dataclass SmartReport:    available, error, model, percent_used, available_spare,
                           media_errors, power_on_hours, data_units_written, tb_written
@dataclass SwapReport:     total_mb, used_mb, free_mb
@dataclass DiskReport:     mount, size_gb, used_gb, avail_gb, pct_used, pct_free
@dataclass GhostProcess:   pid, ppid, name, age_seconds, rss_mb
@dataclass ProcessReport:  ghosts: list[GhostProcess], total_ide_processes: int
@dataclass StateDir:       key, path, exists, size_bytes, note           # e.g. vscdb size
@dataclass StateDirReport: dirs: list[StateDir], total_bytes
@dataclass Finding:        pillar(monitor|clean|optimize), severity(info|warn|critical),
                           code, title, detail, recommendation
@dataclass HealthReport:   timestamp, smart, swap, disk, processes, statedirs, host_ram_gb
```

All collectors take an optional `runner` callable (defaults to `_run.run_cmd`) so tests inject
fixtures without touching the real system. No collector raises on failure; it returns a report
with `available=False`/`error` set or an empty list plus a note.

## 4. Pillar Details

### 4.1 Monitor (collectors + analyze)

Maps 1:1 to the article's symptom map:

| Article mechanism | Collector | Default threshold (config key) |
|---|---|---|
| SSD wear | `smartctl` Percentage Used, Available Spare, Media/Data errors, Power-On Hours, Data Units Written → TB | critical if media_errors > 0; critical if NVMe Critical Warning ≠ 0, or available_spare below the device-reported threshold (see the monitor-expansion spec) or health != PASSED (`smart.*`) |
| Swap pressure | `sysctl vm.swapusage` | warn ≥ 8 GB used, critical ≥ 16 GB (`swap.warn_gb`, `swap.crit_gb`) |
| Headroom | `df` on data volume | warn < 15% free, critical < 10% (`disk.warn_free_pct`, `disk.crit_free_pct`) |
| Ghost processes | `ps` — processes whose name matches IDE patterns (Cursor, Code, Claude, Windsurf, Zed, Electron helpers) with age > `procs.ghost_days` (3 d) or total count > `procs.warn_count` (20) | warn |
| State growth | `statedirs` + history deltas | warn state.vscdb ≥ 2 GB (`state.vscdb_warn_gb`), growth ≥ 1 GB/day (`state.growth_warn_gb_day`), total state ≥ 20 GB (`state.total_warn_gb`) |
| Write storms | history delta of Data Units Written between samples ≥ `smart.writes_warn_gb_day` (default 300 GB/day, the article's "pathological" figure) | warn |

Health score: 100 − weighted penalties (critical 25, warn 8, info 0), floor 0. Letter grade
A/B/C/D/F at 90/75/60/40.

### 4.2 Alert (alerts.py)

- `osascript -e 'display notification ...'` per warn/critical finding; info findings never notify.
- Cooldown: per finding `code`, default 24 h (`alerts.cooldown_hours`), state in
  `~/.local/share/wtfssd/alert_state.json`. Notification failure → print to stdout, never crash.
- `watch` mode: loop every `watch.interval_minutes` (default 60), append history, analyze, alert.
  `--once` runs a single pass (what the LaunchAgent calls).

### 4.3 Clean (cleaners.py)

Safety model (from the article's two rules: quit the app first; copy before delete):

1. **Dry-run by default.** `wtfssd clean` only prints sizes. `--apply` performs.
2. **Trash, not `rm`.** Applied items move to `~/.Trash` (name-suffixed on collision) — reversible.
   `--hard` skips Trash (explicit opt-in only).
3. **Running-app guard.** If the owning app (e.g. Cursor) is running, the target is skipped with a
   message unless `--force`.
4. **Backup-first for databases.** `state.vscdb` targets copy the file to
   `~/.local/share/wtfssd/backups/<timestamp>/` before moving to Trash.
5. **Denylist.** Paths under `~/Documents`, `~/Desktop`, `~/Pictures`, home root itself, and any
   path outside `$HOME` are refused outright.

Targets (each: id, title, paths, risk level, owner-app guard, notes):

- `cursor-caches` — Application Support/Cursor/{Cache,CachedData,CachedExtensionVSIXs,Code Cache,logs,Service Worker}; guard: Cursor.
- `cursor-vscdb-backups` — `state.vscdb.backup*` (not the live DB); guard: Cursor.
- `cursor-vscdb` — live `state.vscdb`; **opt-in only** (`wtfssd clean cursor-vscdb --apply`),
  backup-first, guard: Cursor; warns that local chat history is lost.
- `cursor-snapshots` — files matching `*.pack` under `~/.cursor` and under
  `Application Support/Cursor/CachedData`; report-only in v1 unless `--apply` with guard
  (they regenerate — the optimize pillar is the real fix).
- `claude-caches` — Application Support/Claude caches/logs; guard: Claude. (`~/.claude` transcripts
  are user data: report-only, never a clean target.)
- `xcode-deriveddata` — `~/Library/Developer/Xcode/DerivedData/*`; no guard.
- `xcode-devicesupport` — `iOS DeviceSupport/*`; no guard.
- `user-caches` — the 10 largest dirs under `~/Library/Caches` ≥ 500 MB
  (config `clean.caches_top_n`, `clean.caches_min_mb`); guard: none (caches are regenerable).
- `node-modules-stale` — `node_modules` under `projects` roots untouched ≥ `clean.node_stale_days`
  (30); guard: none.
- `trash` — empty `~/.Trash`; only with `--apply` (and it is the one irreversible target — labeled).

### 4.4 Optimize (optimize.py)

- `wtfssd optimize ignore [path …]` — write/merge `.cursorignore` at given project roots
  (default: cwd) with: `node_modules/`, `dist/`, `build/`,
  `.next/`, `out/`, `*.log`, `.turbo/`, `coverage/`. Merge = append missing lines under a
  `# wtfssd` marker block; never clobbers user content.
- `wtfssd optimize headroom` — prints current free %, the 15–25% floor, and the top space
  consumers among monitored targets with the exact `wtfssd clean <id>` command for each.
- `wtfssd optimize install-agent` / `uninstall-agent` — writes
  `~/Library/LaunchAgents/com.wtfssd.watch.plist` running `wtfssd watch --once` hourly
  (`StartInterval` 3600), `launchctl bootstrap/bootout` to load/unload.
- SMART habit: `watch` emits an info finding on the 1st of each month reminding to review wear
  trend (`wtfssd history`).

## 5. CLI Surface

```
wtfssd scan [--json] [--no-history] [--fast]   full health report; appends to history by default
wtfssd watch [--once] [--interval N] [--fast]  monitor loop (or single pass) + alerts
wtfssd clean [target …] [--apply] [--hard] [--force] [--json]
wtfssd optimize ignore [path …] | headroom | install-agent | uninstall-agent
wtfssd history [--last N] [--json]           trend table: TB written, % used, free space, swap
wtfssd config --show | --path                effective config
```

`scan` and `watch` accept `--fast`: fast tier only — skips the slow collectors
(state-dir sizing, APFS snapshots, backup readiness, crash logs). See the
monitor-expansion spec for the tier split.

Exit codes: 0 ok / no findings; 1 warnings only; 2 any critical; 3 usage/internal error.
`scan` exits 1/2 so it can drive `watch` and cron-style alerting.

## 6. Config

`~/.config/wtfssd/config.json`, deep-merged over built-in defaults (every threshold in §4.1/4.2/4.3
is a key). Missing file = defaults. Invalid JSON = warning + defaults, never a crash.

## 7. Error Handling

- `run_cmd`: 15 s timeout, `shell=False`; returns stdout whenever the process produced non-empty
  output, regardless of exit code (required because smartctl exits 4 with valid data on Apple
  Silicon); returns `None` on missing binary, timeout, OSError, UnicodeDecodeError, or empty stdout;
  callers translate to `available=False` reports or note-bearing findings.
- Any collector failure still yields a complete report (partial data + note findings) — the tool
  exists to reduce panic, so it must never be a source of it.
- All file mutations confined to: `~/.config/wtfssd/`, `~/.local/share/wtfssd/`,
  `~/Library/LaunchAgents/com.wtfssd.watch.plist`, explicit Trash moves, explicit ignore-file
  merges. Nothing else. Ever.

## 8. Testing

- stdlib `unittest` only. Run: `python3 -m unittest discover -s tests -v`.
- Collectors: fixture-text parsing tests (fixtures captured from this Mac's real
  `smartctl`/`sysctl`/`df`/`ps` output) + failure-path tests (runner returns None).
- analyze/cleaners/optimize/alerts/history: synthetic models + `tempfile.TemporaryDirectory`
  sandboxes; alerts tested with a stub notifier; no test touches the real `$HOME` (env vars
  overridden).
- CLI: smoke tests via `cli.main(argv)` with mocked collectors.
- Verification gate before "done": full suite green + a real `python3 -m wtfssd scan` and
  `python3 -m wtfssd clean` (dry-run) executed on this machine and eyeballed.

## 9. Build Plan (agents)

Interfaces are frozen by `models.py` + this spec, so work splits into independent units:

1. Foundation: pyproject, package skeleton, `models.py`, `_run.py`, `config.py` (+tests).
2. Collectors: `smart`, `swap`, `disk`, `processes`, `statedirs` (+fixtures +tests).
3. Brain: `analyze.py`, `report.py`, `history.py`, `alerts.py` (+tests).
4. Action: `cleaners.py`, `optimize.py` (+tests).
5. Integration: `cli.py`, `__main__`, README; full suite + live `scan`/dry-run `clean` on this Mac.

(1) lands first; (2)(3)(4) run in parallel against the frozen contracts; (5) integrates.
