# wtfssd

**Why is my Mac’s SSD busy / full / “dying”?**

A **zero-dependency Python 3 CLI for macOS** that answers that question
honestly: SMART wear from the drive itself, plus swap, free space, ghost IDE
helpers, and agentic tool state — then alerts, cleans regenerable junk safely,
and reduces indexer churn.

The usual story after heavy agentic coding is not a dead soldered SSD. It’s
**unbounded local state and process lifecycle mess**. `wtfssd` measures that
and gives you a safe way to mop up.

**CLI only.** No supported menu bar app. Optional: one hourly LaunchAgent for
notifications. Full recipes: **[COMMANDS.md](COMMANDS.md)**.

---

## Requirements

- macOS (Apple Silicon primary; Intel varies for SMART)
- Python 3.10+
- Optional: [smartmontools](https://www.smartmontools.org/)  
  `brew install smartmontools` — without it, everything else still works

---

## Install

```sh
git clone https://github.com/ogprotege/wtfssd.git && cd wtfssd
python3 -m wtfssd scan          # run from source, no install

# or:
pipx install .
wtfssd scan
```

Legacy command name `ssdwtf` still works after install (same entry point).

---

## Quick start

```sh
wtfssd scan                          # full health report
wtfssd clean                         # dry-run: what could be reclaimed
wtfssd clean cursor-caches --apply   # actually clean (→ Trash)
wtfssd optimize ignore ~/my-project  # .cursorignore to cut indexer churn
wtfssd optimize install-agent        # optional: one hourly notify scan
```

| Need | Command |
|------|---------|
| Cheap vitals (~0.1s) | `wtfssd scan --micro` |
| Medium check | `wtfssd scan --fast` |
| Full diagnose | `wtfssd scan` |
| Include Xcode/Docker/Caches sizes | `wtfssd scan --bulk-state` |
| Trends | `wtfssd history` |
| Daily summary | `wtfssd digest` |
| Config | `wtfssd config --show` |

Exit codes (`scan` / `watch --once` / `digest`): **0** ok · **1** warnings ·
**2** critical · **3** error.

→ **All workflows, clean targets, agent modes, paths:** [COMMANDS.md](COMMANDS.md)

---

## Safety

- **`clean` is dry-run by default** — nothing moves until `--apply`
- **Trash, not `rm`** (unless you pass `--hard --apply`)
- **App guards** — skips targets if Cursor/Claude/etc. appear running
- **Backup-first** for the live Cursor chat database
- **Denylist** — never touches home root, Documents/Desktop/media folders, or paths outside `$HOME`
- Monitoring commands only write history/metrics/alerts under `~/.local/share/wtfssd`

---

## Configuration

Optional file: `~/.config/wtfssd/config.json` (deep-merged over defaults).

```json
{
  "swap": { "warn_gb": 4.0 },
  "projects": ["/Users/you/code"],
  "watch": { "agent_mode": "hourly" }
}
```

See `wtfssd config --show` and [COMMANDS.md](COMMANDS.md) for keys people
actually change.

---

## What it looks at (short)

| Area | Examples |
|------|----------|
| Drive | SMART % used, media errors, TB written |
| Memory | Swap, pressure, long-lived IDE helpers |
| Storage | Free %, AI tool state dirs, optional bulk (Xcode/Docker/…) |
| Stability | Crashes, thermal throttle, uptime, backup readiness |
| Optional | Secrets-at-rest paths (opt-in), git dirtiness on configured repos |

Collectors are **read-only** (except your explicit `clean` / `optimize` actions).

---

## Tests

```sh
python3 -m unittest discover -s tests -v
```

No network, no root, no third-party packages.

---

## License

MIT

## Docs map

| Doc | Audience |
|-----|----------|
| [COMMANDS.md](COMMANDS.md) | **You at the keyboard** (workflows + flags) |
| [AGENTS.md](AGENTS.md) | Coding agents working in this repo |
| [docs/superpowers/specs/](docs/superpowers/specs/) | Design specs (resource-ethical v2 is current for tiers/agents) |
