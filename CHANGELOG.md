# Changelog

All notable changes to **wtfssd** are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)-style,
dates in UTC calendar days as used by this repo.

The package version remains **0.1.0** until a formal release cut.

---

## [Unreleased]

### Added

- **Top disk writers collector** (`collectors/writers.py`) — per-process
  cumulative bytes written via `ps` + libproc `proc_pid_rusage` (the same
  root-free source as Activity Monitor's "Bytes Written" column). Full tier
  only. New `== TOP DISK WRITERS ==` report section states the honest
  caveat: live processes only — exited processes take their counters away.

### Changed

- **`smart.write_rate` cross-references swap** — when swap is measured and
  low, the finding no longer blames "swap thrash"; it points at state churn,
  cloud-sync daemons, and indexers, and names the top visible writer when
  attribution is available.
- **`procs.many` names its offenders** — the IDE-process warning now lists
  the top process families by count (e.g. `Claude Helper (Plugin) ×20`), so
  the number is explainable after the helper tree exits.

### Fixed

- **Time-bomb tests** — `test_metrics` and the `memory.thrash_hint` test in
  `test_analyze` hard-coded July timestamps against wall-clock windows
  (`metrics.series` 7-day cutoff, `_swap_rate_gb_day` 14-day window) and
  began failing in August. Tests now build timestamps relative to now;
  AGENTS.md records the rule. Suite: 240 tests.

### Documentation

- **Scan thoroughness / no-sudo boundary** — README §11, COMMANDS, AGENTS.md,
  and design specs state clearly that full `scan` runs every non-root
  collector the product ships; `sudo` is never used and root-only probes
  (`powermetrics`, `/var/vm`, system-wide `fs_usage`) stay out of product.
- **History guide** — README §12: TIER column, em-dash for unmeasured cells,
  `history --full-only` for comparable STATE/SMART trends.

---

## 2026-08-02

### Added

- **History truthful display** (PR #11) — history table shows scan tier
  (`full` / `fast` / `micro`, `full+b` with bulk); unmeasured STATE/SMART as
  `—` (not zero); `wtfssd history --full-only`; new scans store `scan_tier`
  and `bulk_state` on `HealthReport` / history JSONL.
- **Human operator docs** (PRs #8, #9) — expanded README + COMMANDS workflows.
- **Private-research gitignore** (PR #10) — `IDEA-SSD.txt`,
  `My-tool-mon_ideas.txt`, `WIP.md` stay local-only.

### Changed

- **Resource-ethical v2** (PR #7, earlier same day chain):
  - Allow-list tiers: `--micro` / `--fast` / full default
  - `state.growth` gates (samples, span, sanity cap)
  - AI-core statedirs by default; bulk paths via `--bulk-state`
  - Single hourly LaunchAgent default (`optimize install-agent`)
  - CLI-only product; menubar / SwiftBar marked unmaintained

### Documentation

- Scan coverage matrix and no-sudo claim (PR #12).

---

## 2026-07-30 — initial package

### Added

- Zero-dependency Python 3 macOS CLI: `scan`, `clean`, `watch`, `optimize`,
  `history`, `digest`, `config`.
- Collectors for SMART, swap, disk, processes, statedirs, pressure, system,
  APFS, backup, crashes, write rate, external SMART, churn, FDs, MCP,
  secrets (opt-in), retention, launchd, Spotlight, logs, gitwatch.
- Analyze → findings + health score; alerts; dry-run-by-default cleaners;
  `.cursorignore` / LaunchAgent optimize paths.
- Stdlib unittest suite (later grown through monitor expansion and
  resource-ethical stages).

### Notes

- Package restored from implementation-plan contractual listings after source
  loss; package name stabilized as **wtfssd** (legacy console alias `ssdwtf`).
