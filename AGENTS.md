# AGENTS.md — wtfssd

Guidance for AI coding agents working in this repository. Assumes no prior
knowledge of the project.

## Repository state

Authoritative package: `wtfssd/` (console script `wtfssd`; legacy alias
`ssdwtf`). Operator docs: **`README.md`** (intro) + **`COMMANDS.md`**
(workflows & flags — keep these consistent with `cli.py`). Design:
`docs/superpowers/specs/` (resource-ethical v2 wins on tiers/agents/CLI-only).
Tests: `tests/` (**225** cases). Remote: `https://github.com/ogprotege/wtfssd.git`.

## Project overview

`wtfssd` ("why is my Mac's SSD busy / full / 'dying'?") is a **zero-dependency
Python 3 CLI for macOS** that monitors SSD wear, swap pressure, storage
headroom, ghost IDE processes, and agentic-IDE state growth — then alerts,
cleans safely, and optimizes churn at its source. It operationalizes the
article in `IDEA-SSD.txt` ("My MacBook Aged Three Years in Three Months of
Vibe Coding"): the thesis is that agentic IDEs don't wear out Apple Silicon
SSDs, they drown them in unbounded local state.

Four pillars:

- **Monitor** — SMART wear (`smartctl`), swap (`sysctl`), disk (`df`),
  processes (`ps`), agentic state dirs (`du`-style sizing)
- **Alert** — threshold crossings via macOS Notification Center (`osascript`),
  transition-based: a finding notifies when its code is new, its severity
  escalated since the last notification, or its per-severity cooldown elapsed
  (warn: `alerts.cooldown_hours` 24 h; critical:
  `alerts.cooldown_critical_hours` 4 h); info findings never notify
- **Clean** — dry-run-by-default cleanup of regenerable state (IDE caches,
  chat-DB backups, Xcode DerivedData, stale `node_modules`)
- **Optimize** — `.cursorignore` generation, free-space floor tracking,
  launchd LaunchAgent for scheduled monitoring

Non-goals: GUI / menu bar product, Docker cleanup, remote/fleet monitoring,
Windows/Linux, **any `sudo` / root requirement**. (`menubar/` and
`contrib/swiftbar/` may exist as unmaintained archives only.)

## Scan thoroughness (contractual)

- **Never sudo.** `run_cmd` never prefixes `sudo`; the package must not
  prompt for a password. Root-only tools (`powermetrics`, `/var/vm` listing,
  continuous `fs_usage`) stay **out of product** — document the gap, do not
  half-wrap them.
- **Full `scan` is thorough for agentic/IDE drowning**, not whole-OS forensics.
  Default full tier runs every collector that works without root (see
  `config.DEFAULTS["tiers"]["full"]`). Max in-product pass:
  `scan --bulk-state` (+ optional `secrets`, `git.repos`,
  `smart.external_devices`).
- **Tier ladder:** `micro` (swap/disk/procs/pressure) → `fast` (+ SMART and
  cheap signals) → `full` (+ statedirs, apfs, crashes, churn, fds, logs,
  writerate, …) → `full` + `--bulk-state` (heavy non-AI trees).
- Operator narrative: **README §11** and **COMMANDS.md** “How thorough…”.
  Keep those docs in sync when adding collectors.

## Technology stack

- **Python ≥ 3.10, standard library only.** No pip installs, no third-party
  imports, no venv required. Developed against Python 3.14.6 on macOS arm64.
- Build backend: setuptools (≥ 68); console script `wtfssd = wtfssd.cli:main`.
- External commands (all read-only, never via sudo): `smartctl` (optional —
  `brew install smartmontools`; degrades to "unavailable" when missing),
  `sysctl`, `df`, `ps`, `du`, `osascript`, `launchctl`, plus the other
  collectors’ tools (`tmutil`, `diskutil`, `iostat`, `lsof`, …).
- Targets macOS (Apple Silicon primary; Intel works with varying SMART
  coverage).

## Build and run commands

```sh
python3 -m wtfssd scan                 # full forensic
python3 -m wtfssd scan --micro         # cheapest tier
python3 -m wtfssd scan --fast          # medium tier
python3 -m wtfssd scan --bulk-state    # full + bulk state dirs
python3 -m wtfssd clean                # dry-run
python3 -m wtfssd clean cursor-caches --apply
python3 -m wtfssd optimize ignore ~/my-project
python3 -m wtfssd optimize install-agent   # one hourly agent by default
python3 -m wtfssd watch --once
python3 -m wtfssd history
python3 -m wtfssd digest
python3 -m wtfssd config --show

pipx install .
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_config -v
```

Exit codes: `0` ok · `1` warnings · `2` critical · `3` error.  
Human workflows: **COMMANDS.md** (do not invent flags not listed there / in
`cli.py`).

## Code organization

Per the design spec (`docs/superpowers/specs/2026-07-30-wtfssd-design.md`),
the package layout is:

```
wtfssd/
  __init__.py            # __version__
  __main__.py            # entry: from .cli import main; sys.exit(main())
  cli.py                 # argparse: scan | clean | watch | optimize | history | digest | config
  models.py              # dataclasses shared across all modules (the contract)
  config.py              # load/merge ~/.config/wtfssd/config.json over defaults
  collectors/
    __init__.py
    _run.py              # run_cmd(): subprocess wrapper (timeout, no shell, never raises)
    smart.py             # smartctl -a /dev/disk0 → SmartReport
    swap.py              # sysctl vm.swapusage → SwapReport
    disk.py              # df -k /System/Volumes/Data → DiskReport
    processes.py         # ps → ghost IDE helpers + per-IDE RSS feed → ProcessReport
    statedirs.py         # AI-core dirs by default; bulk (Xcode/Docker/Caches/…) via include_bulk; vscdb → StateDirReport
    pressure.py          # memory pressure: sysctl level + memory_pressure free-% → PressureReport
    system.py            # uptime (kern.boottime), pmset throttle, ioreg battery → SystemReport
    apfs.py              # tmutil local snapshots + diskutil container free → ApfsReport
    backup.py            # tmutil destinationinfo/latestbackup → BackupReport (Time Machine readiness)
    crashes.py           # DiagnosticReports per watched app, trailing 7 days → CrashReport
    writerate.py         # iostat -d current-interval MB/s → WriteRateReport
    smartext.py          # SMART for external drives, bridge protocols in order → SmartReport
    churn.py             # .pack snapshot create/destroy turnover vs stored baseline → ChurnReport
    fds.py               # lsof -nP per-PID open-fd counts → FdsReport
    mcp.py               # claude_desktop_config.json MCP fleet + pgrep liveness → MCPReport
    secrets.py           # OPT-IN key/token scan; paths/lines/rules only, never values → SecretsReport
    retention.py         # retention-config audit (cleanupPeriodDays etc.) → RetentionReport
    launchd.py           # LaunchAgent/Daemon additions vs stored baseline → LaunchdReport
    spotlight.py         # mds/mdworker CPU + mdutil indexing state → SpotlightReport
    logs.py              # ~/Library/Logs sizing + growth leaders → LogsReport
    gitwatch.py          # read-only git status across configured repos → GitWatchReport
  analyze.py             # reports + config + history → list[Finding] + health score 0–100
  history.py             # JSONL scan history; trend / growth-rate analysis
  metrics.py             # sqlite metrics baseline (~/.local/share/wtfssd/metrics.db)
  alerts.py              # Finding → osascript notification; per-severity cooldowns
                         # + escalation transitions; alert_state.json state file
  cleaners.py            # CleanupTarget registry + dry-run/apply engine
  optimize.py            # .cursorignore writer, LaunchAgent plist install/uninstall
                         # (install-agent: one hourly agent by default)
  report.py              # human tables and --json serialization
tests/
  fixtures/              # captured outputs: smartctl.txt, sysctl_swap.txt, df.txt, ps.txt
  test_*.py              # one module per component (see Testing below)
contrib/swiftbar/        # UNMAINTAINED archive (not product)
menubar/                 # UNMAINTAINED archive (not product) — see menubar/UNMAINTAINED.md
```

**Product surface is CLI only.** Do not treat `menubar/` or SwiftBar as
supported deliverables. Optional continuous monitoring is a single LaunchAgent
via `optimize install-agent` (default `watch.agent_mode=hourly`).

Data flow: collectors → `models.HealthReport` → `analyze` → `[Finding]` +
score → `report` (text | json); `history.append`, `metrics.record`, and
`alerts.notify` branch off the same findings — every scan/watch pass appends
JSONL history AND records metrics to `~/.local/share/wtfssd/metrics.db`
(`scan --no-history` does neither).
`cleaners` sizes targets from collectors then dry-runs
or Trashes; `optimize` writes ignore files / LaunchAgent plists.

## Code style guidelines

These are contractual, from the implementation plan's global constraints:

- **Python standard library ONLY.** Never add third-party dependencies.
- `from __future__ import annotations` at the top of every module; type hints
  on all public functions. Line endings LF.
- **External commands are invoked only via `collectors._run.run_cmd`**
  (never `shell=True`, never direct `subprocess` elsewhere).
- **Collectors never raise.** Every failure degrades gracefully — return a
  report with `available=False`/`error` or empty lists plus a `note`.
- Dataclasses in `models.py` are **contractual** — do not add,
  remove, or rename fields without updating every consumer and test.
  (They are plain `@dataclass`, not frozen — `collectors/smart.py`'s parser
  mutates fields while building a report.)
- Every collector accepts an optional `runner` callable (defaults to
  `_run.run_cmd`) so tests inject fixtures without touching the real system.

## Testing instructions

- Framework: **stdlib `unittest`** only. No pytest, no network, no root.
- Run from the repo root: full suite `python3 -m unittest discover -s tests -v`;
  single module `python3 -m unittest tests.test_<name> -v`.
- Collector parsers are tested against captured real command output in
  `tests/fixtures/` (`smartctl.txt`, `sysctl_swap.txt`, `df.txt`, `ps.txt`),
  injected via fake `runner` callables — tests must never shell out to the
  real system.
- Filesystem-touching tests (cleaners, optimize, history, config) run against
  `tempfile.TemporaryDirectory` and fakes; `cli` tests use `unittest.mock` to
  patch `build_report`, `analyze`, history, and config paths.
- The suite is **225 tests, all passing** (resource-ethical v2: allow-list
  tiers, growth gates, AI/bulk statedirs, single LaunchAgent, CLI-only).
  Operator docs: `README.md` + `COMMANDS.md`.

## Configuration and runtime state

- User config: `~/.config/wtfssd/config.json` — deep-merged over code
  defaults; only set keys are overridden. Inspect with `wtfssd config --show`
  (path: `wtfssd config --path`). Useful keys: `swap.warn_gb`, `swap.crit_gb`,
  `disk.warn_free_pct`, `procs.ghost_days`, `state.vscdb_warn_gb`,
  `state.growth_min_samples`/`state.growth_min_days`/`state.growth_max_gb_day`,
  `state.include_bulk_default`, `smart.device`, `smart.external_devices`,
  `alerts.cooldown_hours`, `alerts.cooldown_critical_hours`,
  `watch.interval_minutes`, `watch.fast_interval_minutes`,
  `watch.agent_mode` (`hourly` default | `fast` | `both` | `none`),
  `projects` (dirs scanned for stale `node_modules`),
  `tiers.micro`/`tiers.fast`/`tiers.full` (collector **allow-lists** for
  `--micro` / `--fast` / full; writerate only on full; statedirs AI-core on
  full, bulk via `--bulk-state`), `backup.enabled`/`backup.warn_hours`/
  `backup.crit_hours`, `apfs.snapshot_warn_days`, `pressure.sustained_min`,
  `crashes.warn_weekly`/`crashes.apps`, `thermal.warn_below`,
  `uptime.warn_days`, `writerate.warn_mb_s`, `battery.capacity_info_pct`,
  `procs.leak_warn_mb_h`/`procs.leak_window_h`,
  `churn.warn_turnover`/`churn.warn_gb`, `fds.warn_count`, `mcp.config_path`,
  `secrets.enabled` (opt-in, defaults off — scanner never records values),
  `spotlight.warn_cpu_pct`, `logs.warn_gb_day`/`logs.extra_dirs`,
  `git.repos`/`git.warn_changes`/`git.warn_unpushed`.
- Runtime state (the only writes monitoring makes):
  `~/.local/share/wtfssd/` — `history.jsonl`, `metrics.db`,
  `alert_state.json`, `churn_state.json`, `launchd_baseline.json`,
  `watch.log` / `watch-fast.log` (LaunchAgent stdout/stderr), `backups/`.
  Both exist on the development machine.

## Safety model (security considerations)

`wtfssd` deletes files by design, so these rules are load-bearing — preserve
them in any change to `cleaners.py`:

- **Dry-run by default.** `clean` never touches a file without `--apply`.
- **Trash, not `rm`.** Applied cleans move items to `~/.Trash`;
  `--hard` deletes permanently only when explicitly requested.
- **App guards.** Cleaning a target whose owning app is running is skipped
  with an explanation; `--force` overrides.
- **Backup-first.** High-risk targets (the Cursor chat database) are copied
  to `~/.local/share/wtfssd/backups/` before removal.
- **Denylist.** Paths outside the user's home directory, the home directory
  itself, and `Documents`/`Desktop`/`Movies`/`Music`/`Pictures` are never
  touched.
- **Read-only monitoring.** `scan`, `watch`, `history`, and `config` only
  read the system.
- **Secrets scanner is opt-in.** `secrets.enabled` defaults to `false`; even
  when enabled it records only file paths, line numbers, and rule names —
  never the matched values.
- Never run external commands with `shell=True`; never require `sudo`
  (smartctl works without it on Apple Silicon for the internal NVMe; if it
  fails, report `available=False` — do not wrap with sudo).

## Development workflow notes

- The project was built with superpowers subagent-driven development: spec →
  plan → 12 tasks, each with a brief and review report under
  `wtfssd/.superpowers/sdd/`. When changing behavior, consult
  `docs/superpowers/specs/2026-07-30-wtfssd-design.md` first and keep it in
  sync.
- The plan file mandates running **only your own test module** during
  development, not the whole suite, when working in parallel.
- No CI configuration exists; verification is the local unittest suite plus
  manual live runs (`python3 -m wtfssd scan`) on macOS.
- Git: `origin` points at `https://github.com/ogprotege/wtfssd.git`. Do not
  commit or push unless explicitly asked.
