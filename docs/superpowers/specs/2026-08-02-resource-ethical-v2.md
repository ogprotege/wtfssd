# wtfssd — Resource-Ethical v2 Spec

Companion to `2026-07-30-wtfssd-design.md` and `2026-07-30-monitor-expansion.md`.
Where this document disagrees with the expansion spec on continuous sampling
cadence, tier membership, or product surface, **this document wins**.

## Purpose

Keep the forensic value of wtfssd while ensuring continuous presence never
becomes a meaningful fraction of the machine's background I/O or CPU.

## Product posture (CLI-only)

1. **wtfssd is a CLI product.** Supported surface: `scan`, `watch`, `clean`,
   `optimize`, `history`, `digest`, `config` — plus optional Notification Center
   alerts from `watch` / LaunchAgent.
2. Default use is **on-demand** (run a command when you care).
3. Continuous presence is optional: **at most one** LaunchAgent
   (`optimize install-agent`, default `hourly`).
4. Full directory walks and 1-second iostat samples are **not** for frequent
   polling — use `scan --micro` / `scan --fast` when you want cheap checks.
5. **Native menu bar app is out of product scope.** Tree may remain under
   `menubar/` as **unmaintained archive** only. Do not document it as
   supported. Do not install it at login. SwiftBar under `contrib/swiftbar/`
   is likewise optional/unmaintained.

## Tiers (allow-list)

| Tier | Flag | Collectors (default) | Budget |
|------|------|----------------------|--------|
| micro | `--micro` | swap, disk, processes, pressure | < 100 ms |
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
- `fast`: fast agent only (explicit)
- `both`: legacy dual agents (explicit opt-in; print a resource warning)
- `none`: write nothing; print guidance to use on-demand `scan` / `watch`

Do not stack multiple continuous pollers.

## Growth findings

`state.growth` requires:
- ≥ `state.growth_min_samples` (default 4) full statedirs samples
- span ≥ `state.growth_min_days` (default 3.0) days between first and last
- absolute rate ≤ `state.growth_max_gb_day` sanity cap (default 50); above cap → suppress

## Non-goals (this version)

- Native menu bar / GUI product maintenance
- Token/cost tracking, multi-device sync
- **Any `sudo` / root requirement** — monitors that only work as root
  (`powermetrics`, `/var/vm` listing, continuous `fs_usage`) stay out of
  product. Document the gap; do not half-wrap them.
- Write-latency probes that write to the SSD to measure it
- New clean mutation surfaces beyond existing targets

## Thoroughness claim

Default `scan` (full tier) is thorough for **agentic/IDE drowning** signals
without root. Maximum in-product pass is `scan --bulk-state` plus optional
config (`secrets`, `git.repos`, `smart.external_devices`). It is **not** a
claim of “every macOS metric possible.”
