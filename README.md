# wtfssd

Why is my Mac's SSD busy / full / "dying"? A zero-dependency Python 3 CLI that
monitors SSD wear, swap pressure, storage headroom, ghost IDE processes, and
agentic-IDE state growth — then alerts you, cleans safely, and fixes the churn
at its source. It also watches memory pressure, uptime, thermal throttle and
battery state, APFS local snapshots, Time Machine backup readiness, IDE crash
frequency, live write rate, and external drives — plus per-process RSS leak
slopes, open-file-descriptor counts, the MCP server fleet, indexer snapshot
churn, retention-config posture, launchd persistence changes, Spotlight
indexer load, log growth, and uncommitted/unpushed work across your git
repos. An opt-in secrets scanner (off by default) flags API keys and tokens
left lying in agent state — it reports file, line, and rule name only, never
the secret itself.

It exists because of the vibe-coding SSD panic: after months of heavy agentic
coding (dozens of parallel agents, IDEs scaffolding apps autonomously), developers
started blaming their soldered-in SSDs for machines that ran hot, beachballed,
and filled up. The field data tells a different story — drives reporting
"PASSED" at 2% wear after 54 TB written, while the *software* around them
drowns: 25 GB of swap on a 16 GB machine, Cursor helper processes alive for 27
days, a `state.vscdb` chat database growing ~1 GB/day with no retention policy,
and indexer snapshot churn that regenerates the moment you delete it. The SSD
was never dying; it was trapped inside an unhealthy software environment.
`wtfssd` measures all of that directly — SMART wear from the drive's own
counters, not vibes — and gives you the cleanup and guardrails the IDEs don't.

## Requirements

- macOS on Apple Silicon (Intel Macs work, but SMART coverage varies)
- Python 3.10+ — no third-party dependencies, standard library only
- [smartmontools](https://www.smartmontools.org/) for ground-truth SSD wear:
  `brew install smartmontools` (without it everything else works; the SMART
  section reports "unavailable")

## Install

From source, no install needed:

```sh
git clone <this repo> && cd wtfssd
python3 -m wtfssd scan
```

Or install the `wtfssd` command into an isolated environment:

```sh
pipx install .
wtfssd scan
```

## Quick start

```sh
wtfssd scan              # full health report: SMART, storage, swap, ghost
                         # processes, agentic-state sizes, findings, health score
wtfssd scan --json       # same, machine-readable
wtfssd scan --fast       # fast tier only (skips state-dir sizing, APFS
                         # snapshots, crashes, churn, fds, secrets,
                         # logs, gitwatch); watch --fast likewise
wtfssd clean             # dry-run: lists what *would* be cleaned, deletes nothing
wtfssd clean cursor-caches --apply   # actually clean (moves to Trash)
wtfssd optimize ignore ~/my-project  # write/merge .cursorignore churn rules
wtfssd optimize headroom             # free-space floor status + top consumers
wtfssd optimize install-agent        # background monitoring: two LaunchAgents,
                                     # hourly full watch + 5-min fast-tier watch
wtfssd watch --once      # single monitor pass + Notification Center alerts
wtfssd history           # trend table built from past scans
wtfssd digest            # one-look daily summary: domain statuses, key deltas
                         # (TB written, swap, state, logs, backup age), findings
wtfssd digest --json     # same, machine-readable (--days N widens the window)
wtfssd config --show     # effective config (defaults + your overrides)
```

Exit codes for `scan` / `watch --once` / `digest`: `0` no findings,
`1` warnings only, `2` any critical finding, `3` internal error. `clean`
exits `0`, or `3` on an unknown target.

## Menu bar app

`menubar/` is a native Swift menu bar app (SwiftUI popover, no
dependencies) that puts the health score and grade in the menu bar —
`SSD 92·A`, colored green/yellow/red by the worst current finding. The
popover shows a hero score + grade, a VITALS strip, all ten domains with
status markers, the current findings, and Full Scan / Digest / Quit
actions (scan and digest open in Terminal). It refreshes every 60 seconds
from `wtfssd scan --fast --json --no-history`; everything it does is
read-only.

```sh
cd menubar && ./build.sh        # builds build/WTFSSDMonitor.app
open build/WTFSSDMonitor.app
```

The app prefers an installed `wtfssd` command; from a source checkout it
falls back to `python3 -m wtfssd` with the repo root as working directory
(the repo path is baked into the app at build time, so rebuild if you move
the checkout).

A SwiftBar/xbar plugin alternative remains at
`contrib/swiftbar/wtfssd.5m.py` — same data, rendered as a text dropdown
inside SwiftBar instead of a native popover.

## Safety model

`wtfssd` is built to be less scary than the problem it diagnoses:

- **Dry-run by default.** `clean` never touches a file unless you pass `--apply`.
- **Trash, not `rm`.** Applied cleans move items to `~/.Trash` so you can
  inspect and restore. `--hard` deletes permanently only when you ask for it.
- **App guards.** Cleaning a target whose owning app is running (e.g. Cursor)
  is skipped with an explanation; `--force` overrides.
- **Backup-first.** High-risk targets (the Cursor chat database) are copied to
  `~/.local/share/wtfssd/backups/` before removal.
- **Denylist.** Paths outside your home directory, your home directory itself,
  and `Documents`/`Desktop`/`Movies`/`Music`/`Pictures` are never touched.
- **Read-only monitoring.** `scan`, `watch`, `history`, and `config` only read
  the system; the only writes are scan history, the metrics baseline, alert
  state, and churn/launchd baselines under `~/.local/share/wtfssd`.
- **Opt-in secrets scanning.** The secrets scanner does nothing unless you
  set `secrets.enabled: true`. It reports only the file path, line number,
  and which rule matched — the matched value is never displayed or stored.

## Configuration

Defaults live in the code; override any of them in
`~/.config/wtfssd/config.json` (see the path with `wtfssd config --path`).
Only the keys you set are overridden — everything is deep-merged with defaults.

Example — alert on swap earlier than the 8 GB default:

```json
{
  "swap": { "warn_gb": 4.0, "crit_gb": 12.0 }
}
```

Other useful keys: `disk.warn_free_pct`, `procs.ghost_days`,
`procs.leak_warn_mb_h` / `procs.leak_window_h` (RSS leak-slope alert),
`state.vscdb_warn_gb`, `smart.device`, `smart.external_devices` (extra drives
to probe, e.g. `["/dev/disk2"]`), `alerts.cooldown_hours` /
`alerts.cooldown_critical_hours` (per-severity re-notify intervals, 24 h / 4 h),
`watch.interval_minutes` / `watch.fast_interval_minutes` (hourly full agent /
5-minute fast-tier agent), `projects` (directories scanned for stale
`node_modules`), `tiers.fast` / `tiers.slow` (which collectors `--fast` keeps
and skips), `backup.enabled` / `backup.warn_hours` / `backup.crit_hours`
(Time Machine freshness), `apfs.snapshot_warn_days`,
`pressure.sustained_min`, `crashes.warn_weekly` / `crashes.apps`,
`thermal.warn_below`, `uptime.warn_days`, `writerate.warn_mb_s`,
`battery.capacity_info_pct`, `churn.warn_turnover` / `churn.warn_gb`
(snapshot churn), `fds.warn_count`, `mcp.config_path`,
`secrets.enabled` (**opt-in — defaults to `false`**; the scanner reports
paths, line numbers, and rule names only, never the matched values),
`spotlight.warn_cpu_pct`, `logs.warn_gb_day` / `logs.extra_dirs`,
`git.repos` (repositories watched for uncommitted/unpushed work) /
`git.warn_changes` / `git.warn_unpushed`. Run `wtfssd config --show` for the
full merged picture.

## How it works

- `wtfssd/collectors/` — read-only probes: SMART (`smartctl`, including the
  NVMe critical-warning flag and the device-reported spare threshold), swap
  (`sysctl`), disk (`df -k`, 1K-blocks converted to decimal GB), processes
  (`ps`, including the per-IDE RSS feed behind leak-slope detection), agentic
  state dirs (`du`-style sizing of an 18-entry categorized registry with a
  double-count guard for nested paths), memory pressure
  (`sysctl` / `memory_pressure`), uptime / thermal throttle / battery
  (`sysctl` / `pmset` / `ioreg`), APFS local snapshots (`tmutil`), Time
  Machine readiness (`tmutil destinationinfo`), crash frequency
  (`~/Library/Logs/DiagnosticReports`), write rate (`iostat`), SMART for
  external drives, snapshot churn (`.pack` create/destroy turnover vs a
  stored baseline), open-fd counts (`lsof`), the MCP server fleet
  (`claude_desktop_config.json` cross-checked with `pgrep`), retention-config
  posture (e.g. `cleanupPeriodDays`), launchd persistence (LaunchAgent/Daemon
  diff vs a stored baseline), Spotlight indexer load (`ps` / `mdutil`), log
  growth (`~/Library/Logs` sizing), uncommitted/unpushed work (read-only
  `git status` over configured repos), and the opt-in secrets scanner.
- `wtfssd/analyze.py` — turns a report + history into severity-ranked
  findings, plus a status for each of the ten domains shown above the
  findings: drive, backup, headroom, memory, processes, state, stability,
  telemetry, privacy, work (`ok` / `warn` / `critical`, or `unknown` when a
  domain's collectors returned no data — absence of data is never reported
  as `ok`). Memory-pressure warnings fire only when elevated pressure is
  *sustained* — a majority of samples over `pressure.sustained_min`
  minutes — so a momentary spike doesn't alert; level-4 critical pressure
  always fires immediately.
- `wtfssd/history.py` — JSONL scan history for trend and growth-rate analysis.
- `wtfssd/metrics.py` — sqlite baseline store
  (`~/.local/share/wtfssd/metrics.db`); every scan/watch pass records its
  metrics there alongside the JSONL history.
- `wtfssd/alerts.py` — Notification Center via `osascript`, transition-based
  so it doesn't nag: a finding notifies when it's new, when its severity
  escalates since the last notification (a warn→critical jump notifies
  immediately, even inside the warn cooldown), or when its per-severity
  cooldown elapses — warn findings re-notify at most every
  `alerts.cooldown_hours` (24 h), critical ones every
  `alerts.cooldown_critical_hours` (4 h). Info findings never notify.
- `wtfssd/cleaners.py` — guarded, dry-run-first cleanup targets.
- `wtfssd/optimize.py` — `.cursorignore` merging and the LaunchAgents
  (hourly full watch plus a 5-minute fast-tier watcher).
- `wtfssd/cli.py` — the `wtfssd` command.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

No network, no root, no third-party packages required. Tests that touch the
filesystem run against temporary directories and fakes.

## License

MIT
