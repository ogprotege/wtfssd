# ssdwtf — Monitor Expansion Design Spec

Companion to `2026-07-30-ssdwtf-design.md` (the base spec). Everything in the
base spec still holds; this document extends it. Where the two disagree, this
document wins and the base spec should be patched in the same change.

Source requirements: `My-tool-mon_ideas.txt` (30 specced monitors + monitoring
inventory) diffed against the shipped v0.1.0. The package name stays
`ssdwtf` — pyproject, tests, and the console script all use it; `wtfssd` is
only the repo/checkout name.

## 1. Purpose

Turn the v0.1.0 on-demand scanner into a **continuous monitoring system**: a
tiered sampler with a baseline store, rate-of-change alerting across twelve
independent health domains, and (Phase 3) a menu-bar presence. The driving
principle from the research: never confuse SSD endurance, storage capacity,
memory pressure, software churn, and backup safety — they are separate
domains, and a green SSD score must never conceal a red backup warning.

## 2. Constraints (unchanged unless noted)

- Python ≥ 3.10, **standard library only**. No pip installs. (`sqlite3` is
  stdlib and is used for the metrics store.)
- **No sudo, ever.** Monitors that require root (`powermetrics`, `/var/vm`
  listing, `fs_usage`) are rejected; every chosen monitor has a no-sudo
  source. A latency probe that writes to the SSD to measure it is rejected
  as self-defeating.
- All collectors read-only, invoked only via `collectors._run.run_cmd`,
  never `shell=True`, never raise, all accept an optional `runner`.
- New external commands (all read-only, all present on stock macOS except
  where noted): `memory_pressure`, `pmset -g therm`, `ioreg`,
  `tmutil`, `diskutil`, `iostat`, `sysctl kern.boottime`,
  `sysctl kern.memorystatus_vm_pressure_level`, `lsappinfo` (Phase 2),
  `lsof` (Phase 2), `mdutil` (Phase 2), `mdfind` (Phase 2).
- Safety model of the base spec is unchanged; this expansion adds **no new
  mutation surface** in Phase 1 (pure monitoring). The secrets scanner
  (Phase 2) is opt-in, local, and reports paths/classifications only —
  never secret values.

## 3. Architecture changes

### 3.1 Tiered sampling

Collectors split into two tiers (config: `tiers.fast` list, `tiers.slow`
list, with defaults below). `scan` runs both tiers (back-compatible);
`scan --fast` runs only the fast tier — sub-second, safe to run every
30–60 s from a menu-bar poller or `watch --fast`.

- **fast** (cheap counters, no directory walks): smart, swap, disk,
  processes, pressure, system (uptime/throttle/battery), writerate
- **slow** (walks or multi-second commands): statedirs, apfs, backup,
  crashes, plus Phase 2 (churn, fds, mcp, secrets, logs, spotlight,
  retention, launchd audit)

`watch` gains `--fast`; the LaunchAgent keeps calling `watch --once`
(full). A second, more frequent LaunchAgent for the fast tier is a Phase 3
decision (menu bar poller may replace it).

### 3.2 Metrics store (metrics.py — new)

Stdlib `sqlite3` at `~/.local/share/ssdwtf/metrics.db`. One table:

```sql
CREATE TABLE IF NOT EXISTS samples (
  ts TEXT NOT NULL,          -- ISO-8601 local, same as HealthReport.timestamp
  metric TEXT NOT NULL,      -- dotted name, e.g. "swap.used_gb"
  value REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_metric_ts ON samples(metric, ts);
```

Public API (the only consumers are cli/watch and analyze):

- `record(report: HealthReport, path: Path | None = None) -> None` —
  flattens a HealthReport into the canonical metric set (§3.3) and inserts
  one row per metric. Never raises.
- `series(metric: str, days: float, path: Path | None = None) -> list[tuple[str, float]]`
- `rate_per_day(metric: str, days: float, path: Path | None = None) -> float | None`
  — linear fit (least squares) over the window; `None` if < 2 points.
- `latest(metric: str, path: Path | None = None) -> float | None`

history.jsonl stays as-is for `history`/trend rendering; the metrics store
is additive, written alongside history on every scan/watch pass.

### 3.3 Canonical metrics (Phase 1 set)

```
smart.percent_used, smart.tb_written, smart.media_errors, smart.available_spare,
swap.used_gb, disk.pct_free, disk.avail_gb, procs.ghost_count, procs.total_ide,
state.total_gb, state.vscdb_gb,
pressure.level,                       # 1=normal 2=warn 4=critical (sysctl)
system.uptime_days, system.cpu_speed_limit, battery.cycle_count, battery.max_capacity_pct,
writerate.mb_s,                       # iostat disk0, sampled
apfs.local_snapshot_count, apfs.container_free_gb,
backup.last_backup_age_hours, backup.destination_present,   # 1/0
crashes.weekly_count                  # watched apps, rolling 7d
```

### 3.4 Evidence labels on findings

`Finding` gains one field: `evidence: str = "measured"` — one of
`measured | derived | correlated | inferred | reported | unavailable`.
Default keeps every existing test valid. Report renders the label for
non-measured findings. New rate-of-change findings are `derived`;
cross-metric blame ("swap likely driving writes") is `inferred`.

### 3.5 Domain dashboard (replaces single-score-only presentation)

`analyze` keeps the 0–100 score/grade (back-compat) and additionally
returns per-domain statuses. `report.render_text` prints a domain table
above the findings; `--json` gains a `domains` object.

Phase 1 domains: `drive` (smart + external), `backup`, `headroom`,
`memory` (swap + pressure), `processes`, `state`, `stability` (crashes +
throttle + uptime), `telemetry` (writerate, battery). Status per domain:
`ok | warn | critical | unknown`, = worst finding severity mapped into that
domain; `unknown` when its collectors were unavailable. A critical in any
domain makes overall exit code 2 as today.

## 4. New collectors (Phase 1)

All in `ssdwtf/collectors/`, all with module-level `parse_*` (pure) +
`collect_*` (runner-injected) following the smart.py pattern. New frozen
dataclasses added to models.py (additive, with defaults — see §7).

| Collector | Source | Report | Key fields |
|---|---|---|---|
| `pressure.py` | `sysctl -n kern.memorystatus_vm_pressure_level`; `memory_pressure` (fallback parse) | `PressureReport` | `available, error, level (1/2/4), free_pct` |
| `system.py` | `sysctl kern.boottime`; `pmset -g therm`; `ioreg -rn AppleSmartBattery` | `SystemReport` | `available, uptime_days, cpu_speed_limit (100 = none), battery_cycle_count, battery_max_capacity_pct, battery_present` |
| `apfs.py` | `tmutil listlocalsnapshots /`; `diskutil info <disk.mount>` | `ApfsReport` | `available, snapshot_count, oldest_snapshot_days, container_free_gb, volume_used_gb` |
| `backup.py` | `tmutil destinationinfo`; `tmutil latestbackup` | `BackupReport` | `available, configured, destination_present, last_backup_age_hours, destinations: list[str]` |
| `crashes.py` | `~/Library/Logs/DiagnosticReports/*.ips` (pure pathlib, no runner) | `CrashReport` | `available, weekly: dict[app, int], total_weekly` |
| `writerate.py` | `iostat -d -w 1 -c 2 disk0` (second sample is the rate) | `WriteRateReport` | `available, mb_per_s` |
| `smartext.py` | `smartctl -a -d auto <dev>` fallback `-d sat` per configured external device | `SmartReport` (reused) | same fields; `available=False` when unmounted/absent |

`smart.py` is also extended (same task as smartext): parse `Critical
Warning`, `Available Spare Threshold`, `Unsafe Shutdowns`, and composite
`Temperature` from NVMe output into new SmartReport fields
(`critical_warning: int | None`, `spare_threshold: int | None`,
`unsafe_shutdowns: int | None`, `temperature_c: int | None`).

### New/updated findings (analyze.py)

| Finding | Severity | Rule (config key) |
|---|---|---|
| `smart.critical_warning` | critical | NVMe Critical Warning ≠ 0 |
| `smart.spare_low` | critical | spare < spare_threshold (was: < 100 — **fixed**, the old rule cried wolf) |
| `backup.none_configured` | critical | no TM destination (`backup.enabled` = true) |
| `backup.stale` | warn / critical | last backup older than `backup.warn_hours` (48) / `backup.crit_hours` (168) |
| `backup.destination_missing` | warn | configured but not mounted |
| `apfs.snapshots_old` | warn | local snapshot older than `apfs.snapshot_warn_days` (7) |
| `pressure.warn` / `pressure.critical` | warn / critical | current level ≥ 2 / = 4 (sustained-for-`pressure.sustained_min` logic deferred to Phase 3, when the metrics store has accumulated real samples) |
| `memory.thrash_hint` | inferred warn | swap.used_gb rising (rate > 0.5 GB/day) AND pressure ≥ 2 in same window |
| `crashes.frequent` | warn | any watched app > `crashes.warn_weekly` (3) in 7 days |
| `thermal.throttling` | warn | cpu_speed_limit < 100 |
| `battery.wear` | info | max_capacity < `battery.capacity_info_pct` (90%) — informational only (cycle-delta tracking deferred to Phase 3 baselines) |
| `uptime.restart_hint` | inferred warn | uptime > `uptime.warn_days` (14) AND swap.used_gb ≥ swap.warn_gb |
| `writerate.storm` | warn | mb_per_s > `writerate.warn_mb_s` (200) — sustained check arrives with baselines |
| `smart.external_unhealthy` | critical | any configured external device: health ≠ PASSED, media errors, or critical warning |

## 5. Config additions (merged over DEFAULTS, back-compatible)

```json
"tiers":   {"fast": ["smart","swap","disk","processes","pressure","system","writerate"],
            "slow": ["statedirs","apfs","backup","crashes"]},
"pressure": {"sustained_min": 10},
"apfs":     {"snapshot_warn_days": 7},
"backup":   {"enabled": true, "warn_hours": 48, "crit_hours": 168},
"crashes":  {"warn_weekly": 3, "apps": ["Cursor", "Code", "Claude", "Windsurf"]},
"thermal":  {"warn_below": 100},
"uptime":   {"warn_days": 14},
"writerate": {"device": "disk0", "warn_mb_s": 200},
"battery":  {"capacity_info_pct": 90},
"smart":    {"device": "/dev/disk0", "writes_warn_gb_day": 300.0,
             "external_devices": []}
```

## 6. CLI surface (Phase 1 additions)

- `ssdwtf scan [--json] [--fast]` — `--fast` runs the fast tier only;
  skipped slow collectors appear in JSON as `available: false` with
  `note: "not collected (--fast)"`, never as zero.
- `ssdwtf watch [--once] [--fast]` — same tier split.
- Exit codes unchanged (0/1/2/3). `unknown` domains do not affect exit code.

## 7. models.py changes (additive — the only contract edit)

New optional fields on `HealthReport`, all with defaults so every existing
construction site and test keeps working:

```python
pressure: PressureReport = field(default_factory=lambda: PressureReport(available=False))
system: SystemReport = field(default_factory=lambda: SystemReport(available=False))
apfs: ApfsReport = field(default_factory=lambda: ApfsReport(available=False))
backup: BackupReport = field(default_factory=lambda: BackupReport(available=False))
crashes: CrashReport = field(default_factory=lambda: CrashReport(available=False))
writerate: WriteRateReport = field(default_factory=lambda: WriteRateReport(available=False))
external_smart: list[SmartReport] = field(default_factory=list)
```

`report_to_dict` / `report_from_dict` handle the new fields (asdict works;
from_dict ignores unknown/missing keys for forward/backward tolerance).
`Finding` gains `evidence: str = "measured"` as in §3.4.

## 8. Phases

- **Phase 1 (this spec's first plan):** metrics store, tiers, the seven new
  collectors, smart.py extension, domain dashboard, new findings, config,
  `--fast`. Pure monitoring; no new mutations. PR 1.
- **Phase 2:** RSS-slope leak detection, snapshot-churn turnover, fds, MCP
  fleet accounting, secrets scan (opt-in), retention audit, launchd audit,
  spotlight, logs, expanded state-dir registry + category totals +
  double-count guard, uncommitted-work report. PR 2.
- **Phase 3:** menu-bar presence (SwiftBar plugin reading `--fast` JSON +
  alert state), alert-on-transition semantics with per-severity cooldowns,
  daily digest, fast-tier poller agent. PR 3.

Each phase ends with its spec/plan/README/AGENTS.md in sync with shipped
reality — doc drift is a review defect.

## 9. Testing

Same regime as the base spec: stdlib `unittest`, fixtures captured from real
command output injected via fake runners; filesystem-touching collectors
(crashes) against `tempfile.TemporaryDirectory`; metrics store against
tempdir DBs; no test shells out. New fixtures: `memory_pressure.txt`,
`pmset_therm.txt`, `ioreg_battery.txt`, `tmutil_destinations.txt`,
`tmutil_snapshots.txt`, `diskutil_info.txt`, `iostat.txt`,
`smartctl_external.txt`. Existing 81 tests must keep passing unmodified
except where a task explicitly extends a fixture/model.

---

## 10. Phase 2 detail (this spec's second plan)

Phase 2 adds process-lifecycle depth, privacy/retention auditing, and
work-loss protection. Same constraints: stdlib only, no sudo, never raise,
read-only (the only writes are state files under `~/.local/share/ssdwtf/`).

### 10.1 New collectors

| Collector | Source | Report | Notes |
|---|---|---|---|
| processes.py extension | existing ps parse | `ProcessReport.ide_procs: list[GhostProcess]` (additive field) | every IDE-family process with pid+RSS, not just ghosts — feeds RSS slopes |
| `churn.py` | `*.pack` files under `~/.cursor` + `~/Library/Application Support/Cursor/CachedData` (pure FS) | `ChurnReport` | file set diff vs `churn_state.json`: added+removed between scans = turnover |
| `fds.py` | `lsof -nP` (one run, aggregated per command) | `FdsReport` | per-app open-fd counts, max single pid |
| `mcp.py` | `claude_desktop_config.json` + `pgrep -f` + `ps` | `MCPReport` | declared MCP servers → live pids, RSS, age, orphans (alive while Claude.app dead) |
| `secrets.py` | regex scan of `~/.claude` transcripts, `claude_desktop_config.json`, state.vscdb (sqlite3 read-only) | `SecretsReport` | OPT-IN (`secrets.enabled=false` default). Reports path+line+rule only, NEVER values. Files > 5 MB skipped |
| `retention.py` | static config reads (`~/.claude/settings.json` `cleanupPeriodDays`, Cursor equivalent) | `RetentionReport` | per-tool lifecycle-control posture |
| `launchd.py` | plist filenames in `~/Library/LaunchAgents`, `/Library/LaunchAgents`, `/Library/LaunchDaemons` | `LaunchdReport` | baseline diff via `launchd_baseline.json`; first run stores baseline, no findings |
| `spotlight.py` | `mdutil -s /` + `ps` CPU of mds_stores/mdworker | `SpotlightReport` | indexing state + indexer CPU |
| `logs.py` | size walk of `~/Library/Logs` children + `logs.extra_dirs` | `LogsReport` | total + per-dir sizes; growth via metrics |
| `gitwatch.py` | `git -C <repo> status --porcelain`, `remote`, `log --branches --not --remotes` (all read-only, no network) | `GitWatchReport` | uncommitted/untracked counts, has_remote, unpushed commit count per repo in `git.repos` |

### 10.2 State-dir registry expansion + categories

`statedirs.py`: `StateDir` gains `category: str = ""`. New entries:
zed-app-support, codex-home (`.codex`), jetbrains-app-support,
ollama-models (`.ollama`), lmstudio-cache (`.cache/lm-studio`),
huggingface-cache (`.cache/huggingface`), mlx-cache (`.cache/mlx`),
docker-data (`Library/Containers/com.docker.docker`). Categories:
`ai-state | ide-cache | build-artifacts | models | user-caches | dev-deps`.
`StateDirReport` gains `category_totals: dict[str, int]` and `total_bytes`
becomes double-count-safe: entries whose path is contained in another
tracked entry's path (cursor-vscdb, cursor-vscdb-backups inside
cursor-app-support) are excluded from `total_bytes` (still reported
individually). Existing tests updated accordingly (sanctioned edit).

### 10.3 New findings (all gated on availability)

| Finding | Severity | Rule (config key) | Evidence |
|---|---|---|---|
| `procs.leak` | warn | per-PID RSS slope > `procs.leak_warn_mb_h` (100 MB/h) over `procs.leak_window_h` (6 h) via metrics | derived |
| `state.churn` | warn | pack-file turnover since last scan ≥ `churn.warn_turnover` (20 files) or new size ≥ `churn.warn_gb` (5) | measured |
| `procs.fds` | warn | any watched app fd count ≥ `fds.warn_count` (4000) | measured |
| `mcp.orphan` | warn | MCP server processes alive while Claude.app is not running | measured |
| `mcp.dead` | info | declared server with no live pid while Claude.app IS running | measured |
| `secrets.exposed` | warn | ≥1 match (only when `secrets.enabled`) — title names file+rule, never value | measured |
| `retention.missing` | info | a watched tool has no retention/cleanup setting configured | measured |
| `launchd.new` | warn | new LaunchAgent/Daemon entries vs baseline | measured |
| `spotlight.storm` | warn | mds_stores+mdworker CPU ≥ `spotlight.warn_cpu_pct` (50) | measured |
| `logs.growth` | warn | logs growth ≥ `logs.warn_gb_day` (0.5) via metrics | derived |
| `work.uncommitted` | warn | repo with ≥ `git.warn_changes` (50) changed+untracked files | measured |
| `work.no_remote` | warn | repo with no git remote configured | measured |
| `work.unpushed` | warn | ≥ `git.warn_unpushed` (10) local commits not on any remote | measured |

### 10.4 Domains grow to 10

Add `privacy` (secrets.*, retention.*) and `work` (work.*). `mcp.*` →
processes, `procs.leak`/`procs.fds` → processes, `state.churn`/`logs.*` →
state, `launchd.*` → stability, `spotlight.*` → stability.

### 10.5 Config additions

```json
"procs": {"leak_warn_mb_h": 100, "leak_window_h": 6},
"churn": {"warn_turnover": 20, "warn_gb": 5},
"fds": {"warn_count": 4000},
"mcp": {"config_path": "~/Library/Application Support/Claude/claude_desktop_config.json"},
"secrets": {"enabled": false},
"spotlight": {"warn_cpu_pct": 50},
"logs": {"warn_gb_day": 0.5, "extra_dirs": []},
"git": {"repos": [], "warn_changes": 50, "warn_unpushed": 10}
```

Tiers: fast += retention, launchd, spotlight, mcp (cheap file/probe ops);
slow += churn, fds, secrets, logs, gitwatch.

### 10.6 Metrics additions

`procs.rss.<pid>` (per IDE process, feeds slopes), `churn.turnover`,
`fds.max_count`, `mcp.live_servers`, `logs.total_gb`,
`spotlight.mds_cpu_pct`. Dynamic per-PID metric names are intentional.

---

## 11. Phase 3 detail (menu bar + real-time alerts)

Phase 3 turns the monitor into the always-on tool: menu-bar presence,
transition-based alerting, sustained-pressure detection, daily digest, and a
fast-tier poller agent.

### 11.1 Alert semantics (alerts.py)

- **Per-severity cooldowns**: `alerts.cooldown_hours` (24, warn) and new
  `alerts.cooldown_critical_hours` (4). Info findings never notify (unchanged).
- **Transitions**: a finding notifies when (a) its code is new, (b) its
  severity increased since the last notification for that code, or (c) its
  per-severity cooldown elapsed. State file `alert_state.json` migrates from
  `{code: iso_ts}` to `{code: {"ts": iso, "severity": sev}}`; old format
  entries are read as warn-severity timestamps (back-compatible).

### 11.2 Sustained pressure + thrash window (analyze.py)

- `pressure.warn` fires only when pressure level ≥ 2 is **sustained**:
  majority of `pressure.level` samples over `pressure.sustained_min` (10)
  are ≥ 2, using the metrics store; when metrics are unavailable (no path or
  < 2 samples) it falls back to the current point-in-time behavior.
  `pressure.critical` (level 4) always fires immediately.
- `_swap_rate_gb_day` gains the same 14-day window cap as state growth
  (`window_days: float = 14.0` parameter).

### 11.3 Digest (cli + report)

- `ssdwtf digest [--days N] [--json]` — one-look daily summary from
  metrics + history: period scan count, per-domain current status, key
  deltas (TB written, swap max, state GB, logs GB, backup age), and the
  current findings count by severity. Read-only.

### 11.4 Fast-tier poller agent (optimize.py)

- `install_fast_agent()` writes a second LaunchAgent
  `com.ssdwtf.watch.fast.plist` running `watch --once --fast` every
  `watch.fast_interval_minutes` (5, new config key; StartInterval seconds).
  `optimize install-agent` now installs both agents and prints both results;
  `uninstall-agent` removes both. `install_agent()` signature unchanged.

### 11.5 Menu-bar plugin (contrib/swiftbar/ssdwtf.5m.py)

- SwiftBar/xbar-compatible plugin, stdlib Python 3, executable. Runs
  `ssdwtf scan --fast --json --no-history` (resolves the package by trying
  the `ssdwtf` console script, then `python3 -m ssdwtf` with cwd = repo root
  derived from the plugin's real path). Test hook: `SSDWTF_JSON` env var
  bypasses the subprocess with a canned payload.
- Menu bar title: `SSD:<grade>` colored by worst severity (green/yellow/red/
  gray for unknown). Dropdown: score, ten domains with status markers,
  top 5 findings, action rows (Run full scan in Terminal, Open config,
  Refresh). All actions read-only or Terminal-opening; no silent mutation.
- Install (documented in README): symlink into the SwiftBar plugins dir.

### 11.6 Config additions

```json
"alerts": {"cooldown_critical_hours": 4},
"watch":  {"fast_interval_minutes": 5}
```
