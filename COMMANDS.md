# wtfssd — Commands & workflows

**Name:** `wtfssd` (legacy alias `ssdwtf` still works after `pipx install .`)  
**Run without install:** `python3 -m wtfssd …` from the repo root  
**Config:** `~/.config/wtfssd/config.json` · **Data:** `~/.local/share/wtfssd/`

This is the **operator guide**. For design history, see `docs/superpowers/specs/`.  
For coding agents, see `AGENTS.md`.

---

## What this tool is for

Your Mac feels slow/hot/full after heavy agentic coding. The SSD is usually
**healthy**; the mess is **swap, long-lived IDE helpers, and unbounded local
state**. `wtfssd` measures that, alerts you, and cleans regenerable junk
**safely** (dry-run by default, Trash, app guards).

**CLI only** — no supported menu bar app. Optional background: **one** hourly
LaunchAgent that runs `watch --once` and can notify via Notification Center.

---

## Do this first (5 minutes)

```sh
# 1. See what's wrong
wtfssd scan

# 2. See what you can reclaim (deletes nothing)
wtfssd clean

# 3. Optional: actually clean a safe target
wtfssd clean cursor-caches --apply

# 4. Optional: cut indexer churn in a project
wtfssd optimize ignore ~/path/to/project

# 5. Optional: hourly check + macOS notifications
wtfssd optimize install-agent
```

Exit codes for `scan` / `watch --once` / `digest`:

| Code | Meaning |
|------|---------|
| 0 | OK (no warn/critical findings) |
| 1 | Warnings only |
| 2 | At least one critical finding |
| 3 | Usage or internal error |

---

## Workflows

### A. “Is my drive dying or is software drowning me?”

```sh
wtfssd scan                 # full forensic (recommended)
wtfssd scan --json          # for scripting
wtfssd history              # wear / free space / swap over time
```

Read: SMART % used and health, free %, swap, IDE process count, AI state totals,
backup status, findings at the bottom.

### B. “Free space without doing something stupid”

```sh
wtfssd clean                              # dry-run all safe targets
wtfssd clean cursor-caches --apply        # real clean → Trash
wtfssd clean cursor-vscdb-backups --apply # chat DB backups only
# High risk (loses local chat history) — quit Cursor first:
wtfssd clean cursor-vscdb --apply
```

Rules (always):

- No `--apply` → **nothing is removed**
- Default remove path is **Trash**, not `rm`
- Owning app running → skip unless `--force`
- Chat DB → copied under `~/.local/share/wtfssd/backups/` first

### C. “Stop the machine filling up again”

```sh
wtfssd optimize ignore ~/my-project       # .cursorignore junk paths
wtfssd optimize headroom                  # free % + biggest consumers
```

### D. “Ping me if things get bad” (optional background)

```sh
wtfssd optimize install-agent             # one hourly full watch --once
wtfssd optimize uninstall-agent           # remove agents
```

Prefer **on-demand `scan`** if you don’t want anything scheduled.  
Avoid `--mode both` (two pollers).

### E. “Quick check” vs “deep dive”

| Goal | Command |
|------|---------|
| Seconds-cheap vitals | `wtfssd scan --micro` |
| Medium (SMART, backup, no big walks) | `wtfssd scan --fast` |
| Full diagnose | `wtfssd scan` |
| Full + Xcode/Docker/Caches/models | `wtfssd scan --bulk-state` |
| One-look summary | `wtfssd digest` · `wtfssd digest --days 7` |

**Tiers (plain language):**

| Flag | Includes (roughly) | Avoids |
|------|--------------------|--------|
| `--micro` | swap, free disk, memory pressure, IDE process count | SMART, iostat, directory walks |
| `--fast` | micro + SMART, uptime/throttle/battery, backup, retention, launchd, Spotlight, MCP | statedirs walks, writerate (1s iostat) |
| *(default full)* | fast + AI tool state sizes, APFS, crashes, churn, FDs, logs, git repos, **writerate** | bulk trees unless `--bulk-state` |
| `--bulk-state` | full + Xcode / Docker / HF / general Caches / models | — (slowest) |

If you pass both `--micro` and `--fast`, **micro wins**.

---

## Command reference

### `scan` — diagnose

```sh
wtfssd scan
wtfssd scan --json
wtfssd scan --no-history          # don't write history/metrics
wtfssd scan --micro | --fast
wtfssd scan --bulk-state
```

### `watch` — scan + notifications

```sh
wtfssd watch --once               # one pass (LaunchAgent / cron)
wtfssd watch --once --fast
wtfssd watch                      # loop until Ctrl-C
wtfssd watch --interval 30        # minutes between loops
```

Alerts: new finding, severity escalation, or cooldown elapsed  
(warn default 24h, critical 4h). Info findings never notify.

### `clean` — reclaim space

```sh
wtfssd clean [target …] [--apply] [--hard] [--force] [--json]
```

| Target id | What it is |
|-----------|------------|
| `cursor-caches` | Cursor caches / logs |
| `cursor-vscdb-backups` | Chat DB backup files only |
| `cursor-vscdb` | Live chat DB (history lost) |
| `cursor-snapshots` | Indexer `*.pack` files |
| `claude-caches` | Claude app caches |
| `xcode-deriveddata` | Xcode DerivedData |
| `xcode-devicesupport` | iOS DeviceSupport |
| `user-caches` | Large dirs under `~/Library/Caches` |
| `node-modules-stale` | Old `node_modules` under configured `projects` |
| `trash` | Empty `~/.Trash` (irreversible when applied) |

Default with no targets: all targets marked **safe**.

### `optimize` — prevent recurrence

```sh
wtfssd optimize ignore [dir …]
wtfssd optimize headroom
wtfssd optimize install-agent [--mode hourly|fast|both|none]
wtfssd optimize uninstall-agent
```

| `--mode` | Installs |
|----------|----------|
| `hourly` (default) | `com.wtfssd.watch` → `watch --once` hourly |
| `fast` | `com.wtfssd.watch.fast` → cheap pass on a shorter interval |
| `both` | Both (warning printed — usually a bad idea) |
| `none` | Nothing |

### `history` · `digest` · `config`

```sh
wtfssd history [--last N] [--json]
wtfssd digest [--days N] [--json] [--micro|--fast]
wtfssd config --show              # full merged JSON
wtfssd config --path              # config file location
```

---

## Config people actually change

File: `~/.config/wtfssd/config.json` (deep-merged over defaults).

```json
{
  "swap": { "warn_gb": 4.0, "crit_gb": 12.0 },
  "disk": { "warn_free_pct": 15.0, "crit_free_pct": 10.0 },
  "projects": ["/Users/you/code"],
  "watch": { "interval_minutes": 60, "agent_mode": "hourly" },
  "secrets": { "enabled": false },
  "git": { "repos": ["/Users/you/code/my-app"] }
}
```

| Key | Purpose |
|-----|---------|
| `swap.warn_gb` / `crit_gb` | Swap pressure thresholds |
| `disk.warn_free_pct` / `crit_free_pct` | Free-space floor |
| `projects` | Roots scanned for stale `node_modules` |
| `watch.agent_mode` | `hourly` · `fast` · `both` · `none` |
| `watch.interval_minutes` | Full agent cadence |
| `secrets.enabled` | Opt-in path/line/rule scan (never prints secrets) |
| `git.repos` | Repos for uncommitted/unpushed warnings |
| `smart.external_devices` | e.g. `["/dev/disk2"]` |
| `backup.enabled` | Time Machine domain on/off |

Everything else: `wtfssd config --show`.

---

## Paths

| Path | Role |
|------|------|
| `~/.config/wtfssd/config.json` | Your overrides |
| `~/.local/share/wtfssd/history.jsonl` | Past scans |
| `~/.local/share/wtfssd/metrics.db` | Metric baselines |
| `~/.local/share/wtfssd/alert_state.json` | Notification cooldowns |
| `~/.local/share/wtfssd/backups/` | Pre-clean copies of high-risk DBs |
| `~/Library/LaunchAgents/com.wtfssd.watch*.plist` | Optional agents |

---

## Safety (short)

- **Dry-run by default** on `clean`
- **Trash**, not silent `rm` (unless `--hard --apply`)
- **App running** → skip unless `--force`
- **Chat DB** → backup first
- **Never touch** home root, Documents/Desktop/Pictures/… or paths outside `$HOME`
- **scan / watch / history / config** are read-only (except writing history/metrics/alert state under `~/.local/share/wtfssd`)

---

## Not supported

- Native menu bar app (`menubar/` — unmaintained archive)
- SwiftBar plugin (`contrib/swiftbar/` — unmaintained archive)
- Windows / Linux, Docker cleanup as a product feature, fleet/remote monitoring

---

## Tests (developers)

```sh
python3 -m unittest discover -s tests -v
```
