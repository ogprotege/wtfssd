# wtfssd — Resource-Ethical v2 Spec

Companion to `2026-07-30-wtfssd-design.md` and `2026-07-30-monitor-expansion.md`.
Where this document disagrees with the expansion spec on continuous sampling
cadence or tier membership, **this document wins**.

## Purpose

Keep the forensic value of wtfssd while ensuring continuous presence never
becomes a meaningful fraction of the machine's background I/O or CPU.

## Product posture

1. Default product surface is **on-demand CLI** (`scan`, `clean`, `optimize`,
   `history`, `digest`).
2. Continuous presence is optional and **budgeted**.
3. At most **one** background scheduler may be active by default.
4. Full directory walks and 1-second iostat samples are **not** menu-bar work.

## Tiers (allow-list)

| Tier | Flag | Collectors (default) | Budget |
|------|------|----------------------|--------|
| micro | `--micro` | swap, disk, processes (count only path), pressure | < 100 ms |
| fast | `--fast` | micro + smart, system, backup, retention, launchd, spotlight, mcp | < 500 ms typical |
| full | (default) | fast + statedirs (AI-core), apfs, crashes, churn, fds, secrets, logs, gitwatch, writerate | < 30 s OK |
| bulk | full + `--bulk-state` | full + bulk statedirs (Xcode, Docker, HF, general Caches, models) | weekly / manual |

Implementation: `build_report` uses **allow-lists** from config
(`tiers.micro`, `tiers.fast`, `tiers.full`). `--fast` means “only fast list”
(not “everything not in slow”). `--micro` means “only micro list”.

## Scheduler policy

`optimize install-agent` default mode: `hourly` — one LaunchAgent running
`watch --once` (full) every `watch.interval_minutes` (60).

Modes:
- `hourly` (default): full agent only
- `fast` : fast agent only (explicit)
- `both` : legacy dual agents (explicit opt-in; print a resource warning)
- `none` : write nothing; print guidance for menubar-only users

If the native menubar is the chosen continuous UI, users should run
`uninstall-agent` and let the app own refresh.

## Growth findings

`state.growth` requires:
- ≥ `state.growth_min_samples` (default 4) full statedirs samples
- span ≥ `state.growth_min_days` (default 3.0) days between first and last
- absolute rate ≤ `state.growth_max_gb_day` sanity cap (default 50); above cap → suppress or info-only with evidence=derived

## Menubar

Default refresh: 300 s (5 min). Title/vitals from `--micro --json --no-history`.
Full detail payload: every 3600 s (1 h) or on first open of a detail that needs
statedirs — never every 15 minutes with full walks.

## Non-goals (this version)

Token/cost tracking, multi-device sync, sudo thermal sensors, write-latency
probes, new clean mutation surfaces beyond existing targets.
