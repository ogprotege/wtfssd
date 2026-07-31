# ssdwtf

Why is my Mac's SSD busy / full / "dying"? A zero-dependency Python 3 CLI that
monitors SSD wear, swap pressure, storage headroom, ghost IDE processes, and
agentic-IDE state growth — then alerts you, cleans safely, and fixes the churn
at its source. It also watches memory pressure, uptime, thermal throttle and
battery state, APFS local snapshots, Time Machine backup readiness, IDE crash
frequency, live write rate, and external drives.

It exists because of the vibe-coding SSD panic: after months of heavy agentic
coding (dozens of parallel agents, IDEs scaffolding apps autonomously), developers
started blaming their soldered-in SSDs for machines that ran hot, beachballed,
and filled up. The field data tells a different story — drives reporting
"PASSED" at 2% wear after 54 TB written, while the *software* around them
drowns: 25 GB of swap on a 16 GB machine, Cursor helper processes alive for 27
days, a `state.vscdb` chat database growing ~1 GB/day with no retention policy,
and indexer snapshot churn that regenerates the moment you delete it. The SSD
was never dying; it was trapped inside an unhealthy software environment.
`ssdwtf` measures all of that directly — SMART wear from the drive's own
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
git clone <this repo> && cd ssdwtf
python3 -m ssdwtf scan
```

Or install the `ssdwtf` command into an isolated environment:

```sh
pipx install .
ssdwtf scan
```

## Quick start

```sh
ssdwtf scan              # full health report: SMART, storage, swap, ghost
                         # processes, agentic-state sizes, findings, health score
ssdwtf scan --json       # same, machine-readable
ssdwtf scan --fast       # fast tier only (skips state-dir sizing, APFS
                         # snapshots, backup, crashes); watch --fast likewise
ssdwtf clean             # dry-run: lists what *would* be cleaned, deletes nothing
ssdwtf clean cursor-caches --apply   # actually clean (moves to Trash)
ssdwtf optimize ignore ~/my-project  # write/merge .cursorignore churn rules
ssdwtf optimize headroom             # free-space floor status + top consumers
ssdwtf optimize install-agent        # hourly background monitoring (LaunchAgent)
ssdwtf watch --once      # single monitor pass + Notification Center alerts
ssdwtf history           # trend table built from past scans
ssdwtf config --show     # effective config (defaults + your overrides)
```

Exit codes for `scan` / `watch --once`: `0` no findings, `1` warnings only,
`2` any critical finding, `3` internal error. `clean` exits `0`, or `3` on an
unknown target.

## Safety model

`ssdwtf` is built to be less scary than the problem it diagnoses:

- **Dry-run by default.** `clean` never touches a file unless you pass `--apply`.
- **Trash, not `rm`.** Applied cleans move items to `~/.Trash` so you can
  inspect and restore. `--hard` deletes permanently only when you ask for it.
- **App guards.** Cleaning a target whose owning app is running (e.g. Cursor)
  is skipped with an explanation; `--force` overrides.
- **Backup-first.** High-risk targets (the Cursor chat database) are copied to
  `~/.local/share/ssdwtf/backups/` before removal.
- **Denylist.** Paths outside your home directory, your home directory itself,
  and `Documents`/`Desktop`/`Movies`/`Music`/`Pictures` are never touched.
- **Read-only monitoring.** `scan`, `watch`, `history`, and `config` only read
  the system; the only writes are scan history and alert state under
  `~/.local/share/ssdwtf`.

## Configuration

Defaults live in the code; override any of them in
`~/.config/ssdwtf/config.json` (see the path with `ssdwtf config --path`).
Only the keys you set are overridden — everything is deep-merged with defaults.

Example — alert on swap earlier than the 8 GB default:

```json
{
  "swap": { "warn_gb": 4.0, "crit_gb": 12.0 }
}
```

Other useful keys: `disk.warn_free_pct`, `procs.ghost_days`,
`state.vscdb_warn_gb`, `smart.device`, `smart.external_devices` (extra drives
to probe, e.g. `["/dev/disk2"]`), `alerts.cooldown_hours`,
`watch.interval_minutes`, `projects` (directories scanned for stale
`node_modules`), `tiers.fast` / `tiers.slow` (which collectors `--fast` keeps
and skips), `backup.enabled` / `backup.warn_hours` / `backup.crit_hours`
(Time Machine freshness), `apfs.snapshot_warn_days`,
`pressure.sustained_min`, `crashes.warn_weekly` / `crashes.apps`,
`thermal.warn_below`, `uptime.warn_days`, `writerate.warn_mb_s`,
`battery.capacity_info_pct`. Run `ssdwtf config --show` for the full merged
picture.

## How it works

- `ssdwtf/collectors/` — read-only probes: SMART (`smartctl`, including the
  NVMe critical-warning flag and the device-reported spare threshold), swap
  (`sysctl`), disk (`df -k`, 1K-blocks converted to decimal GB), processes
  (`ps`), agentic state dirs (`du`-style sizing), memory pressure
  (`sysctl` / `memory_pressure`), uptime / thermal throttle / battery
  (`sysctl` / `pmset` / `ioreg`), APFS local snapshots (`tmutil`), Time
  Machine readiness (`tmutil destinationinfo`), crash frequency
  (`~/Library/Logs/DiagnosticReports`), write rate (`iostat`), and SMART for
  external drives.
- `ssdwtf/analyze.py` — turns a report + history into severity-ranked
  findings, plus a status for each of the eight domains shown above the
  findings: drive, backup, headroom, memory, processes, state, stability,
  telemetry (`ok` / `warn` / `critical`, or `unknown` when a domain's
  collectors returned no data — absence of data is never reported as `ok`).
- `ssdwtf/history.py` — JSONL scan history for trend and growth-rate analysis.
- `ssdwtf/metrics.py` — sqlite baseline store
  (`~/.local/share/ssdwtf/metrics.db`); every scan/watch pass records its
  metrics there alongside the JSONL history.
- `ssdwtf/alerts.py` — Notification Center via `osascript`, with per-finding
  cooldown so it doesn't nag.
- `ssdwtf/cleaners.py` — guarded, dry-run-first cleanup targets.
- `ssdwtf/optimize.py` — `.cursorignore` merging and the LaunchAgent.
- `ssdwtf/cli.py` — the `ssdwtf` command.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

No network, no root, no third-party packages required. Tests that touch the
filesystem run against temporary directories and fakes.

## License

MIT
