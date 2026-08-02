# wtfssd — Commands reference

**Canonical package / CLI name:** `wtfssd`  
**Legacy alias (still installed by pipx):** `ssdwtf` → same entry point  
**Module form (no install):** `python3 -m wtfssd …`  
**Config:** `~/.config/wtfssd/config.json` (`wtfssd config --path`)  
**Runtime data:** `~/.local/share/wtfssd/` (history, metrics, alert state, baselines)

This file is the operator cheat sheet. Keep it in sync with `wtfssd/cli.py`
and `wtfssd/config.py`. When names or flags change, update **this file and
README.md together**.

Resource-ethical posture (v2): prefer **on-demand CLI**. Continuous presence
is optional; use **at most one** of menubar or LaunchAgent. Prefer
`scan --micro` for anything polled often.

---

## Invocation

```sh
# From repo root (no install)
python3 -m wtfssd <command> [options]

# After: pipx install .
wtfssd <command> [options]

# Legacy name (same code)
ssdwtf <command> [options]
```

Exit codes (`scan`, `watch --once`, `digest`):

| Code | Meaning |
|------|---------|
| 0 | No warn/critical findings |
| 1 | Warnings only |
| 2 | Any critical finding |
| 3 | Usage / internal error |

`clean` exits 0 on success, 3 on unknown target.

---

## Scan tiers (important)

Collectors are **allow-lists** in config (`tiers.micro` / `tiers.fast` / `tiers.full`).

| Flag | Tier | What runs (defaults) | Target budget |
|------|------|----------------------|---------------|
| `--micro` | micro | swap, disk, processes, pressure | &lt; 100 ms |
| `--fast` | fast | micro + smart, system, backup, retention, launchd, spotlight, mcp | &lt; 500 ms typical |
| *(default)* | full | fast + **AI-core statedirs**, apfs, crashes, churn, fds, secrets, logs, gitwatch, **writerate** | seconds OK |
| `--bulk-state` | full + bulk | also Xcode / Docker / HF / Caches / models (slow walks) | slower full |

- **writerate** (`iostat` ~1 s) runs on **full only**.
- **statedirs** on full default = AI-core only (Cursor, Claude, Codex, VS Code, Windsurf, Zed, …).
- **`--bulk-state`** adds expensive trees: DerivedData, Docker, Hugging Face, `~/Library/Caches`, Ollama, etc.
- `optimize headroom` always sizes with bulk so “what is eating space” stays honest.
- If both `--micro` and `--fast` are set, **micro wins** (stderr warning).

Live check:

```sh
/usr/bin/time -p python3 -m wtfssd scan --micro --no-history >/dev/null
/usr/bin/time -p python3 -m wtfssd scan --fast --no-history >/dev/null
/usr/bin/time -p python3 -m wtfssd scan --no-history >/dev/null
```

---

## `scan` — health report

```sh
wtfssd scan
wtfssd scan --json
wtfssd scan --no-history          # do not append history.jsonl / metrics.db
wtfssd scan --micro               # menu-bar-safe vitals
wtfssd scan --fast                # cheap counters, no statedirs/writerate
wtfssd scan --micro --json --no-history
wtfssd scan --bulk-state          # full + Xcode/Docker/Caches/models sizing
```

---

## `watch` — monitor loop + notifications

```sh
wtfssd watch --once               # single pass + Notification Center
wtfssd watch --once --fast
wtfssd watch --once --micro
wtfssd watch                      # loop; Ctrl-C to stop
wtfssd watch --interval 30        # minutes (overrides config)
```

LaunchAgent (when installed) typically runs `watch --once` on a schedule.

---

## `clean` — safe cleanup (dry-run by default)

```sh
wtfssd clean                      # dry-run all "safe" targets
wtfssd clean cursor-caches        # dry-run one target
wtfssd clean cursor-caches --apply
wtfssd clean cursor-vscdb --apply # high-risk: chat DB; backup-first; quit app first
wtfssd clean --hard --apply       # permanent delete (explicit)
wtfssd clean --force --apply      # ignore "app is running" guard
wtfssd clean --json
```

Known target ids:

| id | Notes |
|----|--------|
| `cursor-caches` | Cursor caches/logs |
| `cursor-vscdb-backups` | `state.vscdb.backup*` only |
| `cursor-vscdb` | Live chat DB — history lost |
| `cursor-snapshots` | `*.pack` indexer snapshots |
| `claude-caches` | Claude app caches |
| `xcode-deriveddata` | Xcode DerivedData |
| `xcode-devicesupport` | iOS DeviceSupport |
| `user-caches` | Large `~/Library/Caches` dirs |
| `node-modules-stale` | Stale `node_modules` under `projects` |
| `trash` | Empty `~/.Trash` (irreversible when applied) |

Rules: dry-run default · Trash not `rm` · app guards · backup-first for vscdb · denylist outside safe paths.

---

## `optimize` — reduce churn / install agents

```sh
wtfssd optimize ignore [path …]   # merge .cursorignore rules (default: cwd)
wtfssd optimize headroom          # free % + top monitored consumers
wtfssd optimize install-agent     # LaunchAgent(s) — see resource-ethical note
wtfssd optimize uninstall-agent   # remove com.wtfssd.watch (+ .fast if present)
```

**Resource-ethical note (v2):** Prefer **CLI on demand** or **one** continuous path.
Do not stack menubar polling + dual LaunchAgents while developing. Stage 4 will
change `install-agent` defaults to a single hourly agent; today the CLI may still
install two agents if you run `install-agent` — avoid that until Stage 4 lands
unless you know you want it.

Labels: `com.wtfssd.watch`, `com.wtfssd.watch.fast` (legacy: `com.ssdwtf.*`).

```sh
# Inspect / unload agents manually
launchctl list | grep wtfssd
launchctl bootout "gui/$(id -u)/com.wtfssd.watch" 2>/dev/null
launchctl bootout "gui/$(id -u)/com.wtfssd.watch.fast" 2>/dev/null
rm -f ~/Library/LaunchAgents/com.wtfssd.watch*.plist
```

---

## `history` — trends

```sh
wtfssd history
wtfssd history --last 20
wtfssd history --json
```

---

## `digest` — one-look daily summary

```sh
wtfssd digest
wtfssd digest --days 7
wtfssd digest --json
```

---

## `config` — effective configuration

```sh
wtfssd config --show              # full deep-merged JSON
wtfssd config --path              # path to user config file
```

### Important config keys (v2)

| Key | Role |
|-----|------|
| `tiers.micro` / `tiers.fast` / `tiers.full` | Collector allow-lists |
| `watch.interval_minutes` | Full watch / hourly agent cadence |
| `watch.fast_interval_minutes` | Fast agent cadence (if used) |
| `watch.agent_mode` | Planned: `hourly` \| `fast` \| `both` \| `none` (Stage 4) |
| `state.growth_min_samples` | Growth gate (Stage 2) |
| `state.growth_min_days` | Growth gate (Stage 2) |
| `state.growth_max_gb_day` | Growth sanity cap (Stage 2) |
| `state.include_bulk_default` | Bulk statedirs default (Stage 3) |
| `secrets.enabled` | Opt-in secrets scan (default `false`) |
| `backup.enabled` | Time Machine domain |

Always: `wtfssd config --show` is truth for your machine.

---

## Menu bar app (Swift)

```sh
cd menubar && ./build.sh
open build/WTFSSDMonitor.app
```

- Package name in UI: **WTFSSD** / `wtfssd-menubar`
- **Do not run** while dual LaunchAgents are also polling (Stage 0 presence A).
- Stage 5 will switch title refresh to `scan --micro` and default 5 min interval.
- Today (pre–Stage 5) the app may still call `scan --fast` every 60 s — leave it closed during resource-ethical work.

SwiftBar alternative: `contrib/swiftbar/wtfssd.5m.py`

---

## Paths cheat sheet

| Path | Purpose |
|------|---------|
| `~/.config/wtfssd/config.json` | User overrides |
| `~/.local/share/wtfssd/history.jsonl` | Scan history |
| `~/.local/share/wtfssd/metrics.db` | SQLite baselines |
| `~/.local/share/wtfssd/alert_state.json` | Notification cooldowns |
| `~/.local/share/wtfssd/churn_state.json` | Snapshot churn baseline |
| `~/.local/share/wtfssd/launchd_baseline.json` | LaunchAgent baseline |
| `~/.local/share/wtfssd/backups/` | Pre-clean DB copies |
| `~/Library/LaunchAgents/com.wtfssd.watch*.plist` | Optional agents |

---

## Tests

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_cli tests.test_config -v
```

---

## Name consistency checklist

When editing docs or code, use **`wtfssd`** for:

- Package import: `from wtfssd import …`
- Console script: `wtfssd`
- Config/data dirs: `~/.config/wtfssd`, `~/.local/share/wtfssd`
- LaunchAgent labels: `com.wtfssd.*`
- Docs titles and examples

`ssdwtf` is **only** a legacy console-script alias in `pyproject.toml`. Historical
plans under `docs/superpowers/plans/2026-07-30-*` still say `ssdwtf`; do not
“fix” those files casually — they are build history. New docs use `wtfssd`.

---

## Related docs

| Doc | Role |
|-----|------|
| [README.md](README.md) | Product overview, install, safety |
| [AGENTS.md](AGENTS.md) | Agent/contributor map of the codebase |
| [docs/superpowers/specs/2026-08-02-resource-ethical-v2.md](docs/superpowers/specs/2026-08-02-resource-ethical-v2.md) | Tier + scheduler policy (v2) |
| [docs/superpowers/plans/2026-08-02-resource-ethical-v2.md](docs/superpowers/plans/2026-08-02-resource-ethical-v2.md) | Staged implementation plan |
