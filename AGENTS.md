# AGENTS.md — ssdwtf

Guidance for AI coding agents working in this repository. Assumes no prior
knowledge of the project.

## Repository state

The package was restored on 2026-07-30 by transcribing the implementation
plan's contractual code listings (the source had been lost from the working
tree; the restoration was reviewed per-module and whole-codebase, 81/81
tests green, live-verified on macOS). The full package source under
`ssdwtf/` is present and authoritative, alongside:

- `pyproject.toml`, `README.md`, `LICENSE` — packaging, docs
- `tests/` — the complete test suite (33 files, 211 tests)
  plus captured command-output fixtures in `tests/fixtures/`
- `docs/superpowers/specs/2026-07-30-ssdwtf-design.md` — the design spec
- `docs/superpowers/plans/2026-07-30-ssdwtf.md` — the implementation plan
  (3128 lines; contains the **exact contractual source** for every module,
  including code listings, per task)
- `ssdwtf/.superpowers/sdd/` — per-task briefs/reports from the original
  build and the restoration (untracked process artifacts, gitignored)

The git remote is `origin → https://github.com/ogprotege/wtfssd.git`. The
checkout directory is named `wtfssd` but the project/package name is
`ssdwtf` — every authoritative artifact (pyproject, tests, spec, plan) uses
`ssdwtf`; do not rename the package to match the directory.

## Project overview

`ssdwtf` ("why is my Mac's SSD busy / full / 'dying'?") is a **zero-dependency
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

Non-goals: GUI, Docker cleanup, remote/fleet monitoring, Windows/Linux.

## Technology stack

- **Python ≥ 3.10, standard library only.** No pip installs, no third-party
  imports, no venv required. Developed against Python 3.14.6 on macOS arm64.
  (This stdlib-only rule applies to the Python package; the menu bar app
  under `menubar/` is a separate Swift artifact — plain Swift, no
  dependencies.)
- Build backend: setuptools (≥ 68); console script `ssdwtf = ssdwtf.cli:main`.
- External commands (all read-only): `smartctl` (optional —
  `brew install smartmontools`; degrades to "unavailable" when missing),
  `sysctl`, `df`, `ps`, `du`, `osascript`, `launchctl`.
- Targets macOS (Apple Silicon primary; Intel works with varying SMART
  coverage).

## Build and run commands

```sh
# Run from source, no install needed (from repo root):
python3 -m ssdwtf scan
python3 -m ssdwtf scan --json
python3 -m ssdwtf clean                       # dry-run, deletes nothing
python3 -m ssdwtf clean cursor-caches --apply # actually clean (moves to Trash)
python3 -m ssdwtf optimize ignore ~/my-project
python3 -m ssdwtf watch --once
python3 -m ssdwtf history
python3 -m ssdwtf digest                      # one-look daily summary (--days N, --json)
python3 -m ssdwtf config --show

# Install the `ssdwtf` command into an isolated environment:
pipx install .

# Run the full test suite (from repo root):
python3 -m unittest discover -s tests -v

# Run a single test module:
python3 -m unittest tests.test_config -v
```

Exit codes for `scan` / `watch --once` / `digest`: `0` no findings,
`1` warnings only, `2` any critical finding, `3` internal error. `clean`
exits `0`, or `3` on an unknown target.

## Code organization

Per the design spec (`docs/superpowers/specs/2026-07-30-ssdwtf-design.md`),
the package layout is:

```
ssdwtf/
  __init__.py            # __version__
  __main__.py            # entry: from .cli import main; sys.exit(main())
  cli.py                 # argparse: scan | clean | watch | optimize | history | digest | config
  models.py              # dataclasses shared across all modules (the contract)
  config.py              # load/merge ~/.config/ssdwtf/config.json over defaults
  collectors/
    __init__.py
    _run.py              # run_cmd(): subprocess wrapper (timeout, no shell, never raises)
    smart.py             # smartctl -a /dev/disk0 → SmartReport
    swap.py              # sysctl vm.swapusage → SwapReport
    disk.py              # df -k /System/Volumes/Data → DiskReport
    processes.py         # ps → ghost IDE helpers + per-IDE RSS feed → ProcessReport
    statedirs.py         # 18 known state dirs (categorized, double-count-guarded), state.vscdb sizes → StateDirReport
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
  metrics.py             # sqlite metrics baseline (~/.local/share/ssdwtf/metrics.db)
  alerts.py              # Finding → osascript notification; per-severity cooldowns
                         # + escalation transitions; alert_state.json state file
  cleaners.py            # CleanupTarget registry + dry-run/apply engine
  optimize.py            # .cursorignore writer, LaunchAgent plist install/uninstall
                         # (install-agent installs both: hourly full + 5-min fast-tier)
  report.py              # human tables and --json serialization
tests/
  fixtures/              # captured outputs: smartctl.txt, sysctl_swap.txt, df.txt, ps.txt
  test_*.py              # one module per component (see Testing below)
contrib/
  swiftbar/ssdwtf.5m.py  # SwiftBar/xbar menu-bar plugin: SSD:<grade> title,
                         # domains/findings dropdown; 5-min scan --fast, read-only
menubar/                 # native menu bar app — separate Swift artifact, NOT
                         # part of the Python package (Swift 6, SwiftPM,
                         # SwiftUI popover, no dependencies)
  Package.swift          # executable target wtfssd-menubar (macOS 13+)
  Sources/wtfssd-menubar/  # main.swift (status item + popover, 60s refresh
                         # from scan --fast --json --no-history; --snapshot /
                         # --dump-menu debug flags), Scanner.swift, PopoverView.swift
  Info.plist             # LSUIElement app metadata; build.sh bakes the repo
                         # root into it and assembles build/WTFSSDMonitor.app
  build.sh               # swift build -c release → build/WTFSSDMonitor.app
```

The menu bar app under `menubar/` is a separate Swift artifact, not part of
the Python package: it is plain Swift with no dependencies, built with
SwiftPM (`cd menubar && ./build.sh`), and drives the CLI read-only
(`scan --fast --json --no-history`).

Data flow: collectors → `models.HealthReport` → `analyze` → `[Finding]` +
score → `report` (text | json); `history.append`, `metrics.record`, and
`alerts.notify` branch off the same findings — every scan/watch pass appends
JSONL history AND records metrics to `~/.local/share/ssdwtf/metrics.db`
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
- The suite is **211 tests, all passing** (verified after the Phase 3
  monitor expansion: alerts, digest, fast-tier agent, SwiftBar plugin).

## Configuration and runtime state

- User config: `~/.config/ssdwtf/config.json` — deep-merged over code
  defaults; only set keys are overridden. Inspect with `ssdwtf config --show`
  (path: `ssdwtf config --path`). Useful keys: `swap.warn_gb`, `swap.crit_gb`,
  `disk.warn_free_pct`, `procs.ghost_days`, `state.vscdb_warn_gb`,
  `smart.device`, `smart.external_devices`, `alerts.cooldown_hours`,
  `alerts.cooldown_critical_hours`, `watch.interval_minutes`,
  `watch.fast_interval_minutes`, `projects` (dirs scanned for stale
  `node_modules`), `tiers.fast`/`tiers.slow` (collector split behind
  `scan --fast`; fast adds `backup`/`retention`/`launchd`/`spotlight`/`mcp`,
  slow carries `statedirs`/`apfs`/`crashes`/`churn`/`fds`/`secrets`/
  `logs`/`gitwatch`), `backup.enabled`/`backup.warn_hours`/`backup.crit_hours`,
  `apfs.snapshot_warn_days`, `pressure.sustained_min`,
  `crashes.warn_weekly`/`crashes.apps`, `thermal.warn_below`,
  `uptime.warn_days`, `writerate.warn_mb_s`, `battery.capacity_info_pct`,
  `procs.leak_warn_mb_h`/`procs.leak_window_h`,
  `churn.warn_turnover`/`churn.warn_gb`, `fds.warn_count`, `mcp.config_path`,
  `secrets.enabled` (opt-in, defaults off — scanner never records values),
  `spotlight.warn_cpu_pct`, `logs.warn_gb_day`/`logs.extra_dirs`,
  `git.repos`/`git.warn_changes`/`git.warn_unpushed`.
- Runtime state (the only writes monitoring makes):
  `~/.local/share/ssdwtf/` — `history.jsonl`, `metrics.db`,
  `alert_state.json`, `churn_state.json`, `launchd_baseline.json`,
  `watch.log` / `watch-fast.log` (LaunchAgent stdout/stderr), `backups/`.
  Both exist on the development machine.

## Safety model (security considerations)

`ssdwtf` deletes files by design, so these rules are load-bearing — preserve
them in any change to `cleaners.py`:

- **Dry-run by default.** `clean` never touches a file without `--apply`.
- **Trash, not `rm`.** Applied cleans move items to `~/.Trash`;
  `--hard` deletes permanently only when explicitly requested.
- **App guards.** Cleaning a target whose owning app is running is skipped
  with an explanation; `--force` overrides.
- **Backup-first.** High-risk targets (the Cursor chat database) are copied
  to `~/.local/share/ssdwtf/backups/` before removal.
- **Denylist.** Paths outside the user's home directory, the home directory
  itself, and `Documents`/`Desktop`/`Movies`/`Music`/`Pictures` are never
  touched.
- **Read-only monitoring.** `scan`, `watch`, `history`, and `config` only
  read the system.
- **Secrets scanner is opt-in.** `secrets.enabled` defaults to `false`; even
  when enabled it records only file paths, line numbers, and rule names —
  never the matched values.
- Never run external commands with `shell=True`; never require `sudo`
  (smartctl works without it on the target platform).

## Development workflow notes

- The project was built with superpowers subagent-driven development: spec →
  plan → 12 tasks, each with a brief and review report under
  `ssdwtf/.superpowers/sdd/`. When changing behavior, consult
  `docs/superpowers/specs/2026-07-30-ssdwtf-design.md` first and keep it in
  sync.
- The plan file mandates running **only your own test module** during
  development, not the whole suite, when working in parallel.
- No CI configuration exists; verification is the local unittest suite plus
  manual live runs (`python3 -m ssdwtf scan`) on macOS.
- Git: `origin` points at `https://github.com/ogprotege/wtfssd.git`. Do not
  commit or push unless explicitly asked.
