# wtfssd — Commands encyclopedia

This is the **full operator manual**: workflows, every command, clean targets,
tiers, agents, config, and troubleshooting for the command line itself.

**New here?** Start with the narrative guide: **[README.md](README.md)**  
(why it exists, first 10 minutes, how to read a report).

---

## Identity

| Item | Value |
|------|--------|
| Canonical command | `wtfssd` |
| Legacy alias | `ssdwtf` (same program after `pipx install .`) |
| From source | `python3 -m wtfssd …` (run inside the repo) |
| Config | `~/.config/wtfssd/config.json` |
| Runtime data | `~/.local/share/wtfssd/` |
| Product shape | **CLI only** — no supported GUI |

---

## Exit codes

Used by `scan`, `watch --once`, and `digest`:

| Code | Meaning | Shell tip |
|------|---------|-----------|
| **0** | No warn/critical findings | “looks clean enough” |
| **1** | At least one **warn**, no critical | worth reading findings |
| **2** | At least one **critical** | act soon |
| **3** | Bad usage or internal error | fix command / report bug |

`clean` exits **0** on success, **3** if you name an unknown target.

---

# Part 1 — Workflows (do these)

## Workflow 1 — First-time health check

```sh
wtfssd scan
```

Then read the **FINDINGS** section and the health grade at the bottom.  
Nothing is deleted.

Optional cheaper passes:

```sh
wtfssd scan --micro      # seconds-cheap vitals only
wtfssd scan --fast       # medium (SMART + system, no big folder walks)
```

## Workflow 2 — Free space carefully

```sh
# 1) See reclaimable junk (dry-run)
wtfssd clean

# 2) Clean one safe target for real (→ Trash)
#    Quit Cursor/Claude first if cleaning their stuff
wtfssd clean cursor-caches --apply

# 3) If free space barely moved:
wtfssd optimize headroom
wtfssd scan --bulk-state          # include Xcode/Docker/Caches sizes
# Empty Trash in Finder
```

## Workflow 3 — Machine feels slow / hot, nothing “open”

```sh
wtfssd scan --micro               # swap + pressure + process count fast
wtfssd scan                       # full picture
```

Typical fixes the findings will suggest:

- **Cmd+Q** IDEs (not only red-button close)  
- Reboot if swap has been high for days  
- Fewer parallel agents / projects  

## Workflow 4 — Keep indexers out of junk

```sh
wtfssd optimize ignore ~/code/my-app
wtfssd optimize ignore ~/code/other-app
```

Opens/creates `.cursorignore` and merges rules under a `# wtfssd` marker.
Safe to re-run (won’t duplicate lines).

## Workflow 5 — Background babysitter (optional)

```sh
wtfssd optimize install-agent       # ONE hourly full check + notify
# …
wtfssd optimize uninstall-agent     # turn off completely
```

Logs (if agent runs): `~/.local/share/wtfssd/watch.log`

## Workflow 6 — “What changed this week?”

```sh
wtfssd history --last 20
wtfssd digest --days 7
wtfssd digest --days 7 --json
```

## Workflow 7 — Scripting / automation

```sh
wtfssd scan --json --no-history
echo $?    # 0 / 1 / 2 / 3
```

Use `--no-history` in tight loops so you don’t grow `history.jsonl` forever.

---

# Part 2 — Scan gears (tiers)

Collectors are **allow-lists** in config (`tiers.micro`, `tiers.fast`, `tiers.full`).

| Flag | Name | What’s included (defaults) | What’s skipped | Typical use |
|------|------|----------------------------|----------------|-------------|
| `--micro` | Micro | swap, free disk, memory pressure, IDE process counts | SMART, iostat, folder walks, almost everything else | “Is it thrashing *right now*?” |
| `--fast` | Fast | micro + SMART, system (uptime/throttle/battery), backup, retention, launchd, Spotlight, MCP | statedirs walks, writerate (1-second iostat), APFS deep, crashes, logs, … | Quick morning check |
| *(none)* | Full | fast + **AI-core state dirs**, APFS snapshots, crashes, churn, FDs, secrets (if on), logs, gitwatch, **writerate**, **top disk writers** | bulk trees (Xcode/Docker/Caches/models) | Real diagnose |
| `--bulk-state` | Full+bulk | full + bulk state dirs | — | “What’s eating the disk?” |

**AI-core state dirs (full default):** Cursor, Claude, VS Code, Windsurf, Zed,
Codex paths (and chat DB sizes).

**Bulk dirs (`--bulk-state` only):** JetBrains, Ollama, LM Studio, Hugging Face,
MLX, Docker Desktop data, Xcode DerivedData, large `~/Library/Caches`.

**Special case:** `wtfssd optimize headroom` always sizes with bulk so the
“biggest consumers” list is honest.

If you pass **both** `--micro` and `--fast`, **micro wins** (stderr warning).

### Timing reality check

On a healthy machine you should see roughly:

| Command | Ballpark |
|---------|----------|
| `scan --micro --no-history` | ~0.1 s |
| `scan --fast --no-history` | under ~1 s |
| `scan --no-history` | a few seconds |
| `scan --bulk-state` | longer if caches are huge |

```sh
/usr/bin/time -p wtfssd scan --micro --no-history >/dev/null
```

---

## How thorough is full scan? (no sudo)

**Product rule: never `sudo`.** Scans never prompt for a password. The code
never invokes `sudo` (collectors go through `run_cmd` only).

Full scan is **complete for every collector we ship that works without root**.
It is not “partial because we forgot sudo” — root-only extras are
deliberately out of product.

### Full tier collectors (default `wtfssd scan`)

`swap`, `disk`, `processes`, `pressure`, `smart`, `system`, `backup`,
`retention`, `launchd`, `spotlight`, `mcp`, `statedirs` (**AI-core only**),
`apfs`, `crashes`, `churn`, `fds`, `secrets` (if enabled), `logs`,
`gitwatch` (if `git.repos` set), `writerate`, `writers` (top disk-writing
processes via libproc — live processes only), plus **external SMART** when
`smart.external_devices` is set.

### Max in-product thoroughness

```sh
brew install smartmontools
# optional: secrets.enabled, git.repos, smart.external_devices, projects
wtfssd scan --bulk-state
```

### Never collected (need root or out of scope)

| Gap | Needs |
|-----|--------|
| SMC die temps / fan continuous | `sudo powermetrics` |
| `/var/vm` swapfile listing | root |
| System-wide fs_usage I/O attribution | root + heavy |
| Whole-disk inventory of every folder | not the product |
| Other users’ homes | privacy / permissions |
| API token *cost* tracking | different product |

Full narrative: [README §11](README.md#11-how-thorough-is-a-scan-coverage--no-sudo).

---

# Part 3 — Command reference

## `scan` — diagnose

```text
wtfssd scan [--json] [--no-history] [--micro] [--fast] [--bulk-state]
```

| Flag | Meaning |
|------|---------|
| *(default)* | Full forensic tier |
| `--json` | Machine-readable JSON (score, domains, findings, raw report) |
| `--no-history` | Do not append `history.jsonl` or `metrics.db` |
| `--micro` | Micro tier |
| `--fast` | Fast tier |
| `--bulk-state` | Full + bulk directory sizing |

Examples:

```sh
wtfssd scan
wtfssd scan --json | python3 -m json.tool | less
wtfssd scan --micro --no-history
wtfssd scan --bulk-state
```

### Reading `TOP DISK WRITERS` (full tier only)

Full scan ranks live processes by **cumulative** disk bytes written,
read from the kernel's own per-process counters (`proc_pid_rusage` —
the same source as Activity Monitor's "Bytes Written" column; no sudo).
Cost per scan: ~40 ms, ~0.5 MB transient memory, ~1.5 KB per history row.

Read it with its limits in mind:

- **Live processes only.** Exited agent/CLI sessions took their counters
  with them — the "visible total" line is a floor, not the machine's total.
- **Cumulative, not a rate.** Divide by the "alive" hours shown next to
  each process.
- **Permission-limited.** Root/system processes it cannot read are
  skipped silently, never estimated.
- **No file paths.** Per-file attribution needs root tracing
  (`fs_usage`) and stays out of product.

Full claims/non-claims table: README §11.

---

## `watch` — diagnose + notify

```text
wtfssd watch [--once] [--interval MIN] [--micro] [--fast] [--bulk-state]
```

| Flag | Meaning |
|------|---------|
| `--once` | One pass, then exit (use this from LaunchAgent) |
| `--interval N` | Loop every N minutes (default from config) |
| tier flags | Same meaning as `scan` |

```sh
wtfssd watch --once
wtfssd watch --once --fast
wtfssd watch --interval 60
```

### When do notifications fire?

Only for **warn** and **critical** findings, when:

1. The finding **code** is new, or  
2. Severity **went up** (warn → critical), or  
3. The per-severity **cooldown** elapsed (default warn 24h, critical 4h)

**Info** findings never notify.

---

## `clean` — reclaim space

```text
wtfssd clean [target …] [--apply] [--hard] [--force] [--json]
```

| Flag | Meaning |
|------|---------|
| *(no --apply)* | **Dry-run only** — print what would happen |
| `--apply` | Perform clean (default: move to `~/.Trash`) |
| `--hard` | Permanent delete (only with `--apply`) |
| `--force` | Ignore “owning app is running” skip |
| `--json` | JSON result objects |

### Target ids

| id | Risk | What it cleans | Notes |
|----|------|----------------|-------|
| `cursor-caches` | safe | Cursor Cache, logs, etc. | Quit Cursor first |
| `cursor-vscdb-backups` | moderate | `state.vscdb.backup*` only | Not the live DB |
| `cursor-vscdb` | **high** | Live `state.vscdb` | **Local chat history gone**; tool backups first; quit Cursor |
| `cursor-snapshots` | moderate | `*.pack` indexer snapshots | Can regenerate |
| `claude-caches` | safe | Claude app caches | Quit Claude first |
| `xcode-deriveddata` | safe | Xcode DerivedData | Rebuild cost = time |
| `xcode-devicesupport` | safe | iOS DeviceSupport | Re-downloads as needed |
| `user-caches` | safe | Largest dirs under `~/Library/Caches` | Config: min size / top N |
| `node-modules-stale` | safe | Old `node_modules` under `projects` | Needs `projects` in config |
| `trash` | special | Empties `~/.Trash` | Irreversible when applied |

No targets listed → all targets with risk **`safe`**.

Examples:

```sh
wtfssd clean
wtfssd clean cursor-caches
wtfssd clean cursor-caches xcode-deriveddata --apply
wtfssd clean cursor-vscdb --apply          # high risk — read the warnings
wtfssd clean trash --apply                 # empty Trash
```

### Safety enforcement (hard-coded)

- Paths outside your home → refused  
- Home directory itself → refused  
- `Documents` / `Desktop` / `Movies` / `Music` / `Pictures` → refused  
- App guard when `guard_app` is running → skip unless `--force`  

---

## `optimize` — prevent recurrence

### `optimize ignore`

```text
wtfssd optimize ignore [dir …]
```

Default dir: current working directory.

```sh
wtfssd optimize ignore
wtfssd optimize ignore ~/code/app1 ~/code/app2
```

### `optimize headroom`

```text
wtfssd optimize headroom
```

Prints free % and the free-space floor (15–25%). If below 15%, lists largest
monitored consumers (with **bulk** sizing so Xcode/caches appear).

### `optimize install-agent`

```text
wtfssd optimize install-agent [--mode hourly|fast|both|none]
```

| Mode | What gets installed |
|------|---------------------|
| `hourly` (**default**) | `com.wtfssd.watch` → full `watch --once` on `watch.interval_minutes` (60) |
| `fast` | `com.wtfssd.watch.fast` → cheap pass on `watch.fast_interval_minutes` |
| `both` | Both agents + **warning** (usually a bad idea) |
| `none` | Installs nothing |

Config default: `"watch": { "agent_mode": "hourly" }`.  
CLI `--mode` overrides config for that invocation only.

```sh
wtfssd optimize install-agent
wtfssd optimize install-agent --mode none
wtfssd optimize install-agent --mode both    # discouraged
```

### `optimize uninstall-agent`

```text
wtfssd optimize uninstall-agent
```

Removes **both** labels if present (`com.wtfssd.watch` and
`com.wtfssd.watch.fast`).

Manual recovery:

```sh
launchctl list | grep wtfssd
launchctl bootout "gui/$(id -u)/com.wtfssd.watch" 2>/dev/null
launchctl bootout "gui/$(id -u)/com.wtfssd.watch.fast" 2>/dev/null
rm -f ~/Library/LaunchAgents/com.wtfssd.watch*.plist
```

---

## `history` — trends

```text
wtfssd history [--last N] [--json] [--full-only]
```

```sh
wtfssd history
wtfssd history --last 30
wtfssd history --full-only      # hide micro/fast rows (comparable STATE/SMART)
wtfssd history --json
```

Built from `~/.local/share/wtfssd/history.jsonl` (rows from past `scan` /
`watch` that did not use `--no-history`).

**How to read the table**

| Column | Meaning |
|--------|---------|
| `TIER` | `full` / `fast` / `micro` (or `fast?` / `micro?` for old rows before tier was stored). `full+b` = full with bulk state dirs |
| `TB WRITTEN` / `WEAR %` | SMART lifetime stats, or `—` if not measured that pass |
| `FREE GB` / `SWAP GB` | Disk free and swap used |
| `STATE GB` | Sized AI/tool state, or `—` if that pass skipped statedirs (**not** “zero state”) |

Do **not** compare `STATE GB` across rows with different tiers. Prefer:

```sh
wtfssd history --full-only
```

A footer note explains how many rows had unmeasured STATE when you show all tiers.

---

## `digest` — one-look summary

```text
wtfssd digest [--days N] [--json] [--micro] [--fast]
```

```sh
wtfssd digest
wtfssd digest --days 7
wtfssd digest --json --days 3
```

Runs a scan (default full), then summarizes domain statuses and key deltas
(TB written, state size, backup age, …).

---

## `config` — settings

```text
wtfssd config --show
wtfssd config --path
```

`--show` is the usual action: full **merged** JSON (defaults + your file).

---

# Part 4 — Configuration people actually change

File: `~/.config/wtfssd/config.json`  
Missing file → all defaults. Invalid JSON → defaults + warning (tool still runs).

### Minimal useful config

```json
{
  "swap": { "warn_gb": 4.0, "crit_gb": 12.0 },
  "disk": { "warn_free_pct": 15.0, "crit_free_pct": 10.0 },
  "projects": ["/Users/YOU/code"],
  "watch": {
    "interval_minutes": 60,
    "agent_mode": "hourly"
  },
  "git": {
    "repos": ["/Users/YOU/code/my-app"]
  },
  "secrets": { "enabled": false }
}
```

### Key reference (operator-relevant)

| Key | Default idea | Purpose |
|-----|--------------|---------|
| `swap.warn_gb` / `crit_gb` | 8 / 16 | Swap used thresholds |
| `disk.warn_free_pct` / `crit_free_pct` | 15 / 10 | Free-space floor |
| `disk.mount` | Data volume path | Which volume `df` checks |
| `procs.ghost_days` | 3 | Age before “ghost” helper |
| `procs.warn_count` | 20 | Too many IDE-related processes |
| `state.vscdb_warn_gb` | 2 | Cursor chat DB size warn |
| `state.total_warn_gb` | 20 | Total AI/tool state warn |
| `state.growth_*` | samples/days/cap | Stops false “GB/day” panic |
| `state.include_bulk_default` | false | Always bulk-size on full if true |
| `watch.interval_minutes` | 60 | Hourly agent period |
| `watch.fast_interval_minutes` | 15 | Fast agent period (if used) |
| `watch.agent_mode` | `hourly` | What `install-agent` installs |
| `alerts.cooldown_hours` | 24 | Warn re-notify spacing |
| `alerts.cooldown_critical_hours` | 4 | Critical re-notify spacing |
| `projects` | `[]` | Roots for stale `node_modules` clean |
| `git.repos` | `[]` | Repos for dirty/unpushed warns |
| `smart.device` | `/dev/disk0` | Internal NVMe path |
| `smart.external_devices` | `[]` | Extra disks for SMART |
| `backup.enabled` | true | Time Machine domain on/off |
| `secrets.enabled` | **false** | Opt-in secrets path scan |
| `tiers.micro` / `fast` / `full` | lists | Collector allow-lists (advanced) |

See everything: `wtfssd config --show`.

---

# Part 5 — Paths & files

| Path | Role |
|------|------|
| `~/.config/wtfssd/config.json` | Your overrides |
| `~/.local/share/wtfssd/history.jsonl` | Past scans (JSON lines) |
| `~/.local/share/wtfssd/metrics.db` | SQLite baselines / rates |
| `~/.local/share/wtfssd/alert_state.json` | Notification cooldowns |
| `~/.local/share/wtfssd/churn_state.json` | Snapshot churn baseline |
| `~/.local/share/wtfssd/launchd_baseline.json` | New LaunchAgent detection |
| `~/.local/share/wtfssd/backups/` | Pre-clean copies of high-risk DBs |
| `~/.local/share/wtfssd/watch.log` | Hourly agent log |
| `~/Library/LaunchAgents/com.wtfssd.watch.plist` | Optional agent |

---

# Part 6 — Troubleshooting the *commands*

### `command not found: wtfssd`

```sh
cd /path/to/wtfssd && python3 -m wtfssd scan
# or
pipx install /path/to/wtfssd
# open a new Terminal after pipx ensurepath
```

### Wrong Python version

```sh
python3 --version    # need 3.10+
```

### Help text

```sh
wtfssd --help
wtfssd scan --help
wtfssd clean --help
wtfssd optimize install-agent --help
```

### Agent installed but never runs

```sh
launchctl list | grep wtfssd
launchctl print "gui/$(id -u)/com.wtfssd.watch"
cat ~/.local/share/wtfssd/watch.log
wtfssd optimize uninstall-agent
wtfssd optimize install-agent
```

### History empty

You only used `--no-history`, or never completed a successful scan, or data
dir was deleted. Run `wtfssd scan` once without `--no-history`.

### JSON parse errors in scripts

Always check exit code; on failure stderr may hold a warning. Prefer:

```sh
wtfssd scan --json --no-history > /tmp/out.json
```

### Still stuck

1. Re-read [README troubleshooting](README.md#12-troubleshooting)  
2. Run `wtfssd scan --json` and inspect `findings`  
3. Open a GitHub issue with OS version, `python3 --version`, and the error  

---

# Part 7 — Safety summary

| Rule | Detail |
|------|--------|
| Dry-run default | `clean` needs `--apply` to change disk |
| Trash default | Recoverable until you empty Trash |
| App guards | Skip if owning app running (unless `--force`) |
| Backup-first | Live chat DB copied under `…/wtfssd/backups/` first |
| Denylist | No escapes outside `$HOME`; no Documents/Desktop/… |
| Monitoring writes | Only history/metrics/alerts/baselines under share dir |
| Secrets | Opt-in; paths/lines/rules only — never values |

---

# Part 8 — Not product

| Path | Status |
|------|--------|
| `menubar/` | Unmaintained archive — do not install |
| `contrib/swiftbar/` | Unmaintained archive — do not install |

---

# Part 9 — Developers

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_cli -v
```

When you change flags in `wtfssd/cli.py`, update **this file and README**
in the same change.

### Related docs

| Doc | Role |
|-----|------|
| [README.md](README.md) | Why + idiot-proof first hour + troubleshooting story |
| [AGENTS.md](AGENTS.md) | Repo map for coding agents |
| [docs/superpowers/specs/2026-08-02-resource-ethical-v2.md](docs/superpowers/specs/2026-08-02-resource-ethical-v2.md) | Current product rules (tiers, agents, CLI-only) |
| [IDEA-SSD.txt](IDEA-SSD.txt) | Source article thesis |
