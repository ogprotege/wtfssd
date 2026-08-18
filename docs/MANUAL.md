# The wtfssd Manual

**“Why is my Mac’s SSD busy / full / ‘dying’?”** — the complete
operator guide. New here? The short version lives on the
[front page](../README.md); every flag lives in [COMMANDS.md](../COMMANDS.md).

A **zero-dependency Python 3 command-line tool for macOS** that answers that
question with measurements, not vibes — then helps you clean up regenerable
junk **safely** and stop the same mess from growing back.

- **No GUI.** Terminal only (on purpose — keep it light).
- **No pip packages.** Standard library only.
- **Deletes nothing unless you say so.** Cleanup is dry-run by default and
  moves files to Trash, not into the void.

If you can open Terminal and copy-paste a line, you can use this.

Full flag encyclopedia and workflows: **[COMMANDS.md](../COMMANDS.md)**.

---

## Table of contents

1. [Why this exists](#1-why-this-exists)
2. [What wtfssd does (and does not)](#2-what-wtfssd-does-and-does-not)
3. [What you need](#3-what-you-need)
4. [Install (caveman mode)](#4-install-caveman-mode)
5. [Your first 10 minutes](#5-your-first-10-minutes)
6. [How to read a scan report](#6-how-to-read-a-scan-report)
7. [Cleaning without panic](#7-cleaning-without-panic)
8. [Stop the mess coming back](#8-stop-the-mess-coming-back)
9. [Optional: hourly check + notifications](#9-optional-hourly-check--notifications)
10. [Scan “gears” (micro / fast / full / bulk)](#10-scan-gears-micro--fast--full--bulk)
11. [How thorough is a scan? (coverage + no sudo)](#11-how-thorough-is-a-scan-coverage--no-sudo)
12. [Reading `history` (truthful trends)](#12-reading-history-truthful-trends)
13. [Configuration for normal humans](#13-configuration-for-normal-humans)
14. [Troubleshooting](#14-troubleshooting)
15. [FAQ](#15-faq)
16. [Safety rules (read once)](#16-safety-rules-read-once)
17. [Where files live](#17-where-files-live)
18. [Docs map & license](#18-docs-map--license)

---

## 1. Why this exists

### The rumor

After months of “vibe coding” (Cursor, Claude Code, dozens of agents, loops
that run for hours), people online claimed **agentic IDEs were killing Mac
SSDs in three months**. Scary SMART screenshots. Soldered storage = dead
laptop. Panic.

### What the article (and real machines) actually found

The story that inspired this tool
(*“My MacBook Aged Three Years in Three Months of Vibe Coding”* — kept
as a local research note, not in the repo) checked the drive’s **own** wear counters:

| Claim | Reality on a heavy agentic machine |
|-------|-------------------------------------|
| SSD is “dying” | SMART often **PASSED**, ~**1–2%** life used |
| Writes are huge | True — tens of TB written — but endurance is still years |
| Machine feels old | True — heat, beachballs, full-disk warnings |

The pain was not NAND wearing out. It was the **software environment**:

1. **Swap pressure** — not enough RAM → kernel writes memory to the SSD
   constantly (the single worst write source on many Macs).
2. **Ghost processes** — close the window with the red button; helpers keep
   living for days or weeks.
3. **Unbounded local state** — chat databases, caches, agent transcripts,
   indexer snapshots with **no retention policy**.
4. **Low free space** — below ~15% free, macOS and the SSD controller both
   struggle (swap, temps, snapshots, everything gets worse).
5. **Non-AI hogs** — Xcode DerivedData, Docker, normal caches — often bigger
   than the AI folders. Fairness matters.

So: **the drive is fine; the house is a mess.**  
`wtfssd` is the broom + the flashlight + the “don’t burn the house down”
checklist.

### Why a CLI, not another menu bar app

A monitoring tool that **itself** polls the disk every minute and walks
huge trees is part of the problem. This product is intentionally:

- **On-demand** by default (`scan` when you care)
- Optionally **one** quiet hourly LaunchAgent if you want notifications
- **Not** a always-on desktop widget

---

## 2. What wtfssd does (and does not)

### Does

| Pillar | Meaning |
|--------|---------|
| **Monitor** | Read SMART, swap, free space, processes, AI state dirs, backup readiness, and more |
| **Alert** | Optional Notification Center pings when something **new** or **worse** shows up |
| **Clean** | Show reclaimable junk; with `--apply`, move it to **Trash** (with guards) |
| **Optimize** | Write `.cursorignore` rules; show free-space floor; install a scheduled check |

### Does not

- Replace Time Machine or back up your life for you  
- Kill processes for you (it **tells** you to quit apps properly)  
- Guarantee the SSD “lasts forever”  
- Run on Windows/Linux  
- Offer a supported menu bar / GUI (folders `menubar/` and `contrib/swiftbar/`
  are **dead experiments** — ignore them)

---

## 3. What you need

| Need | Notes |
|------|--------|
| A Mac | Apple Silicon best; Intel works with patchier SMART |
| Terminal | Applications → Utilities → Terminal |
| Python 3.10+ | `python3 --version` |
| Optional: smartmontools | `brew install smartmontools` for true SSD wear numbers |

Without smartmontools, **everything else still works**; SMART just says
“unavailable / install smartmontools.”

---

## 4. Install (caveman mode)

### Option A — run from a folder (no install)

```sh
cd ~
git clone https://github.com/ogprotege/wtfssd.git
cd wtfssd
python3 -m wtfssd scan
```

Every command below can be written as `python3 -m wtfssd …` instead of
`wtfssd …` if you stay in this folder.

### Option B — install a real command (pipx)

```sh
cd ~/wtfssd          # or wherever you cloned it
pipx install .
wtfssd scan
```

If `pipx` is missing: `brew install pipx && pipx ensurepath`, then open a
**new** Terminal window.

After install, the old name `ssdwtf` still works as an alias. Prefer **`wtfssd`**.

### Option C — already cloned, update after git pull

```sh
cd ~/wtfssd
git pull
pipx install . --force    # only if you used pipx before
```

---

## 5. Your first 10 minutes

Do these **in order**. Copy-paste is fine.

### Step 1 — Look (read-only)

```sh
wtfssd scan
```

Wait a few seconds (full scan often ~2–6 seconds). You get:

- Drive / storage / memory / process / top-disk-writers / state sections  
- A list of **findings** (WARN / CRITICAL / INFO)  
- A **health score** 0–100 and letter grade  

**Nothing was deleted.** Scan only reads the system (and may append a history
row under `~/.local/share/wtfssd/` unless you pass `--no-history`).

### Step 2 — See what cleanup *would* do (still safe)

```sh
wtfssd clean
```

This is a **dry-run**. It prints sizes and “would-trash” lines.  
Your disk is unchanged.

### Step 3 — Clean one safe thing (optional)

Quit Cursor first if you can (less drama).

```sh
wtfssd clean cursor-caches --apply
```

That **moves** cache files to **Trash**. You can restore from Trash if you
panic. Empty Trash yourself later when you trust it.

### Step 4 — Cut indexer churn in a project (optional)

```sh
wtfssd optimize ignore ~/path/to/your/project
```

Adds sensible ignore rules (e.g. `node_modules/`, build dirs) under a
`# wtfssd` marker. Does not delete anything.

### Step 5 — Optional hourly babysitter

```sh
wtfssd optimize install-agent
```

Installs **one** LaunchAgent that runs a full check about once an hour and
can notify you. Uninstall anytime:

```sh
wtfssd optimize uninstall-agent
```

---

## 6. How to read a scan report

You do **not** need to understand every line. Use this decoder.

### Health score / grade

| Grade | Rough meaning |
|-------|----------------|
| A–B | Mostly fine; maybe info/noise |
| C | Real warnings — worth acting this week |
| D–F | Critical issues — free space / backup / drive flags |

Score is a simple penalty system (critical hurts more than warn). It’s a
**compass**, not a medical certificate.

### Domain strip (drive, backup, headroom, memory, …)

Each domain is `ok` / `warn` / `critical` / `unknown`:

| Domain | Think of it as |
|--------|----------------|
| **drive** | Is the SSD itself reporting wear/errors? |
| **backup** | Is Time Machine configured and recent? |
| **headroom** | Do you have enough free space? |
| **memory** | Swap / pressure — is the machine thrashing? |
| **processes** | Too many IDE helpers / ghosts / leaks? |
| **state** | AI tool folders huge or growing fast? |
| **stability** | Crashes, throttle, uptime, weird launchd? |
| **telemetry** | Write rate, battery health notes |
| **privacy** | Retention missing; secrets scan (if enabled) |
| **work** | Dirty git repos you configured |

**Important:** `unknown` means “we couldn’t measure,” **not** “everything is fine.”

### Findings language

```text
[WARN] 54 IDE-related processes running
    Agentic IDEs spawn helper trees that outlive their windows.
    → Fully quit unused IDEs; check Activity Monitor.
```

- **Title** — what fired  
- **Detail** — why it matters  
- **Arrow** — what to do next  

### Common findings and plain-English fixes

| Finding vibe | Likely meaning | What to do |
|--------------|----------------|------------|
| SSD wear low %, PASSED | Drive is fine | Stop doomscrolling; check monthly with `history` |
| Swap high | RAM overflow hitting disk | Quit heavy apps; reboot; fewer parallel agents |
| Many IDE processes / ghosts | Helpers outlived windows | **Cmd+Q** the app; Activity Monitor → force quit leftovers |
| State totals multi‑GB | Chat/state folders huge | `wtfssd clean` dry-run; quit app; clean caches/backups |
| Free space low | Headroom floor breached | Clean + empty Trash; aim for ~15–25% free |
| Backup destination missing | Time Machine disk unplugged | Plug it in or fix TM settings |
| Retention missing | Tools don’t auto-expire chat/state | Set cleanup days in Claude/Cursor settings if available |
| High write volume **and** swap low | Not thrash — state churn, cloud sync, or indexers | Read the `TOP DISK WRITERS` section; `wtfssd clean` dry-run; `optimize ignore` |
| Many IDE processes but you “only use Terminal” | One Electron app in agent mode ≈ 40+ helpers | The finding names the top families (e.g. `Claude Helper (Plugin) ×20`) — Cmd+Q that app |

### Top disk writers (who is writing)

Full scan prints a `TOP DISK WRITERS` section: live processes ranked by
**cumulative** bytes written since each one started. Three reading rules:

1. **Cumulative ≠ rate.** Divide by the "alive" hours shown — 76 GB over
   4 days is background hum; 11 GB over 8 minutes is a download or a storm.
2. **Live processes only.** Exited agent sessions are invisible — the
   "visible total" line is a floor, not the machine's total.
3. **Suspects, not verdicts.** A sync daemon near the top usually means
   *something it syncs* is churning (e.g. agents writing into an
   iCloud-synced Desktop) — fix the churn, not the daemon.

Full capability/limits table: [§11](#11-how-thorough-is-a-scan-coverage--no-sudo).

### SMART in one sentence

**Percentage Used** and **health PASSED** are the honest wear story.  
Huge “TB written” without high % used is **not** an emergency by itself.

---

## 7. Cleaning without panic

### Golden rules

1. **Always dry-run first:** `wtfssd clean` or `wtfssd clean some-target`  
2. **Quit the app** that owns the data (Cursor, Claude, …) when possible  
3. **`--apply` moves to Trash** — recoverable until you empty Trash  
4. **`--hard --apply`** permanently deletes — only if you mean it  
5. Never clean when you don’t understand the target name  

### Safe-ish everyday targets

```sh
wtfssd clean cursor-caches --apply
wtfssd clean claude-caches --apply
wtfssd clean xcode-deriveddata --apply    # rebuild cost: time, not your code
wtfssd clean user-caches --apply          # large Library/Caches dirs
```

### Higher risk

```sh
# Chat DB backups only (not the live DB)
wtfssd clean cursor-vscdb-backups --apply

# LIVE chat database — local history GONE. Quit Cursor. Tool backups first.
wtfssd clean cursor-vscdb --apply
```

### If a clean is skipped

```text
SKIPPED: Cursor appears to be running
```

Quit the app (Cmd+Q), or override with `--force` only if you know why.

### List of target ids

See [COMMANDS.md — clean](../COMMANDS.md#clean--reclaim-space) for the full table
(`cursor-caches`, `xcode-deriveddata`, `trash`, …).

---

## 8. Stop the mess coming back

### Ignore rules (indexer / agent file sprawl)

```sh
wtfssd optimize ignore ~/code/my-app
```

Merges a block of rules (`node_modules/`, `dist/`, logs, …) into
`.cursorignore` without wiping your existing lines.

### Headroom check

```sh
wtfssd optimize headroom
```

Shows free % vs the 15–25% floor and, if you’re low, the biggest monitored
consumers (includes bulk trees like caches so the ranking is honest).

### Habits that beat any tool

1. **Cmd+Q** IDEs when done — don’t only click the red window button  
2. Keep **≥15% free** on the data volume  
3. Reboot occasionally if swap has been high for days  
4. Don’t run 40 agents on an 8 GB / 256 GB base Mac and expect silence  

---

## 9. Optional: hourly check + notifications

```sh
wtfssd optimize install-agent          # one hourly full check
wtfssd optimize uninstall-agent        # remove it
```

What you get:

- LaunchAgent label: `com.wtfssd.watch`  
- Runs roughly: `wtfssd watch --once` each hour  
- Can pop **Notification Center** when a finding is new or gets worse  

What you should **not** do:

```sh
wtfssd optimize install-agent --mode both   # two pollers — avoid
```

Prefer **on-demand `scan`** if you hate background anything.

---

## 10. Scan “gears” (micro / fast / full / bulk)

Think of a car gearbox. Use the lowest gear that answers your question.

| Gear | Flag | When to use | Rough cost |
|------|------|-------------|------------|
| 1 | `--micro` | “Is swap/disk/pressure nuts right now?” | ~0.1 s |
| 2 | `--fast` | Quick SMART + backup + process vibe | under ~1 s typical |
| 3 | *(default)* | Full diagnose including AI folder sizes | a few seconds |
| 4 | `--bulk-state` | Also size Xcode/Docker/Caches/models | slower |

```sh
wtfssd scan --micro
wtfssd scan --fast
wtfssd scan
wtfssd scan --bulk-state
```

**Full default does not walk all of `Library/Caches`.**  
That heavy walk is **`--bulk-state`** (or `optimize headroom`, which always
includes bulk for ranking).

---

## 11. How thorough is a scan? (coverage + no sudo)

### Short answer

**Default `wtfssd scan` is thorough for this product’s job** — “is agentic/IDE
software drowning my Mac?” — **without** asking for your password.

It is **not** a root-level forensic suite of the entire operating system.
That is intentional. “Not everything possible on a Mac” is **not** the same as
“half-finished product.” Full tier already runs **every collector in the
package** that works without root.

| Question | Answer |
|----------|--------|
| Does full scan check “everything on the Mac”? | **No.** |
| Does it check everything in scope for vibe-coding SSD panic? | **Yes — all non-root signals we ship.** |
| Does it use `sudo`? | **Never.** No password prompts. Code path never calls `sudo`. |
| Would sudo make the *product* more complete? | **No.** It would only add root-only extras listed below. |
| Max thoroughness command | `wtfssd scan --bulk-state` + optional config (below) |

### Why no sudo (on purpose)

1. **Safe to run anytime** — no “trust this with root?” moment  
2. **Works the same** for every user account without admin  
3. **Resource ethics** — root tools like continuous `fs_usage` / `powermetrics`
   can themselves hammer the machine  
4. **smartctl on Apple Silicon** usually works **without** sudo for the
   internal NVMe (install smartmontools)

If something truly needs root, the collector is **out of product scope**
rather than half-implemented behind a password.

### What default `scan` (full) *does* check

| Collector | How (no root) | What you learn |
|-----------|---------------|----------------|
| **smart** | `smartctl` on internal disk | Wear %, TB written, health, media errors |
| **swap** | `sysctl vm.swapusage` | Swap pressure (article’s smoking gun) |
| **disk** | `df` on data volume | Free space / headroom floor |
| **pressure** | `sysctl` / `memory_pressure` | Memory pressure level |
| **processes** | `ps` | IDE process count, ghost age, RSS feed |
| **system** | `sysctl` boot time, `pmset` throttle, `ioreg` battery | Uptime, thermal throttle, battery health |
| **backup** | `tmutil` (user-visible) | Time Machine configured? destination present? age? |
| **retention** | Read Claude/Cursor settings files | Cleanup policies missing? |
| **launchd** | List LaunchAgents/Daemons vs baseline | New persistence / relaunchers |
| **spotlight** | `ps` + `mdutil` | Indexer storms |
| **mcp** | Claude desktop config + `pgrep` | MCP fleet / orphans |
| **statedirs** | Walk **AI-core** paths (Cursor, Claude, Codex, …) | Agentic state size |
| **apfs** | `tmutil` / `diskutil` (non-root) | Local snapshot pressure |
| **crashes** | Read `~/Library/Logs/DiagnosticReports` | Crash frequency |
| **churn** | Index snapshot turnover vs baseline | Create/destroy write churn |
| **fds** | `lsof` (what your user can see) | Open-file blowups |
| **logs** | Size `~/Library/Logs` (+ config extras) | Log growth |
| **gitwatch** | `git status` on **configured** repos only (hooks/fsmonitor/gc/filters disabled) | Uncommitted / unpushed work |
| **secrets** | Only if `secrets.enabled: true` | Path/line/rule hits — never values |
| **writerate** | `iostat` (~1 s sample) | Live write MB/s |
| **writers** | `ps` + libproc rusage (Activity Monitor's source) | Which live processes wrote the most bytes (exited processes are invisible — stated in the report) |
| **external SMART** | Only if you list devices in config | External drive health |

### Who is writing? (`writers` — claims and non-claims)

Full scan ranks **live** processes by cumulative disk bytes written and
prints the top of the list:

```text
== TOP DISK WRITERS ==
     76.3 GB  fileproviderd (over 93.4 h alive)
     41.3 GB  cloudd (over 93.4 h alive)
      5.2 GB  com.apple.WebKit.Networking (over 93.4 h alive)
    150.4 GB  visible total across 260 processes
  note: live processes only — exited processes took their write counters with them
```

**Where the numbers come from.** The macOS kernel keeps a lifetime
bytes-written counter for every running process, whether or not anyone
looks at it. Activity Monitor's "Bytes Written" column is a read-out of
that counter; wtfssd reads the very same one (`proc_pid_rusage` via
libproc), once per process, at scan time. Nothing is traced, sampled,
or watched over time — the tool asks for bookkeeping the kernel already
does. No sudo, ever; processes it may not read are skipped silently.

**Cost honesty** (measured on the development machine, M5 Pro, ~260
processes): about **40 ms** per full scan, about **0.5 MB** of memory
while collecting (freed when the scan ends), about **1.5 KB** added to
each full-scan history row. It does not run on `--micro` or `--fast`,
does not write to the metrics database, and never runs on its own in
the background.

| It CAN tell you | It CANNOT tell you |
|---|---|
| Which live processes wrote the most since each one started | Anything about processes that already **exited** — every finished agent/CLI session takes its counter with it |
| That a cloud-sync daemon, Electron app, or indexer is a heavy writer | Writers it lacks permission to read (root/system daemons) — skipped, not estimated |
| A **floor** for attribution (the "visible total" line) | The full accounting of SMART's TB-written — the gap between them is exited + unreadable processes, and on agentic machines that gap is often most of the story |
| Host-level bytes the drive was asked to write | Physical NAND writes after write amplification — only SMART wear % knows that |
| Cumulative bytes plus process age, so you can judge pace | A live **rate** — 76 GB over 4 days is calm; 11 GB over 8 minutes is a storm. Divide by the "alive" hours shown |
| | **Which files or folders** received the writes — per-path attribution needs root tracing (`fs_usage`), which stays out of product |

**Rule of reading:** the list names *suspects*, not the whole crime. If
the visible total is far below what SMART says was written this boot,
the writes came mostly from short-lived processes — on vibe-coding
machines, usually the agent sessions themselves.

### What `--bulk-state` adds

Same as full, **plus** sizing of heavy non-AI trees:

- Xcode DerivedData, Docker Desktop data, Hugging Face / Ollama / LM Studio /
  MLX caches, JetBrains, large `~/Library/Caches`

Use when free space is the question:

```sh
wtfssd scan --bulk-state
wtfssd optimize headroom    # also sizes bulk for ranking
```

### Maximum thoroughness *within* the product (still no sudo)

```sh
brew install smartmontools          # if not installed

# Optional config (~/.config/wtfssd/config.json):
#   "secrets": { "enabled": true }
#   "git": { "repos": ["/Users/YOU/code/app"] }
#   "smart": { "external_devices": ["/dev/disk2"] }
#   "projects": ["/Users/YOU/code"]
#   "logs": { "extra_dirs": ["/path/to/more/logs"] }

wtfssd scan --bulk-state
```

That is the **most complete** scan wtfssd is designed to run.

### What we deliberately do **not** check (needs root or out of scope)

| Not checked | Why | Typical root tool |
|-------------|-----|-------------------|
| Die temps / fan RPM streams | Needs privileged SMC access | `sudo powermetrics` |
| Physical swapfiles under `/var/vm` | Root-only listing | `sudo ls /var/vm` |
| System-wide `fs_usage` / every process I/O | Root + heavy | `sudo fs_usage` |
| Full-disk `du` of entire Macintosh HD | Slow, noisy, not the product | manual `du` |
| Other users’ home directories | Privacy + permissions | — |
| Kernel extensions / SIP deep audit | Different product | — |
| Network sockets / firewall / MDM | Out of scope | — |
| Token/API cost tracking | Different product (e.g. token-monitor) | — |

**You can still run those by hand** when you care:

```sh
# Examples — optional, not part of wtfssd:
sudo powermetrics --samplers smc -n 1
sudo ls -lh /var/vm
```

wtfssd will not wrap them. That keeps the tool password-free and aligned
with “don’t become the workload.”

### So can you “be sure”?

| Claim | Sure? |
|-------|--------|
| SSD wear (if smartmontools works) | Yes — drive’s own SMART |
| Swap / free space / IDE ghosts / AI state sizes | Yes — full scan |
| Which **live** processes wrote the most bytes | Yes — kernel counters; a floor, since exited processes are excluded |
| Biggest non-AI disk hogs | Yes — with `--bulk-state` or `headroom` |
| Everything a root admin could measure | **No** — and we won’t pretend otherwise |
| That missing root checks hide “dying SSD” | Unlikely — SMART + free space + swap cover the article’s failure modes |

---

## 12. Reading `history` (truthful trends)

```sh
wtfssd history                 # all rows: see tiers + dashes
wtfssd history --full-only     # only full (comparable STATE / SMART)
wtfssd history --last 30
```

| Column | Meaning |
|--------|---------|
| **TIER** | `full` / `fast` / `micro` (or `fast?` / `micro?` on old rows before tier was stored). `full+b` = full with bulk dirs |
| **TB WRITTEN / WEAR %** | SMART, or `—` if that pass didn’t collect SMART |
| **FREE / SWAP** | Disk free and swap used |
| **STATE GB** | Sized tool state, or `—` if **not measured** (not “zero state”) |

**Rules of thumb**

1. Prefer **`history --full-only`** when comparing STATE over days.  
2. Ignore `—` cells for trends — those passes skipped that collector.  
3. Big step-changes in STATE often mean **what we count changed** (registry /
   bulk / AI-core), not only that files grew overnight.  
4. New scans after the history update store real `scan_tier` so labels stop
   needing `?`.
5. `TOP DISK WRITERS` is a per-scan snapshot, **not** a trend — each history
   row stores that scan's top list, and `history` does not (yet) chart a
   process's writes across days. Compare rows by eye if you need that today.

---

## 13. Configuration for normal humans

Optional file:

```text
~/.config/wtfssd/config.json
```

Only put keys you care about. Everything else uses built-in defaults.

### Example

```json
{
  "swap": { "warn_gb": 4.0, "crit_gb": 12.0 },
  "disk": { "warn_free_pct": 15.0, "crit_free_pct": 10.0 },
  "projects": ["/Users/you/code"],
  "watch": { "interval_minutes": 60, "agent_mode": "hourly" },
  "git": { "repos": ["/Users/you/code/my-app"] },
  "secrets": { "enabled": false }
}
```

### See what the tool is actually using

```sh
wtfssd config --show
wtfssd config --path
```

More keys: [COMMANDS.md — Config](../COMMANDS.md#configuration-people-actually-change).

---

## 14. Troubleshooting

### “command not found: wtfssd”

```sh
# Either use module form from the repo:
cd /path/to/wtfssd
python3 -m wtfssd scan

# Or install:
pipx install /path/to/wtfssd
# then open a NEW terminal
```

### “SMART unavailable” / missing smartctl

```sh
brew install smartmontools
wtfssd scan
```

Still nothing? Some Macs/permissions limit SMART; the rest of the report is
still useful.

### Scan feels slow

| You ran | Expected |
|---------|----------|
| `scan --micro` | Should feel instant |
| `scan --fast` | Usually under a second |
| `scan` | A few seconds (AI folder sizing) |
| `scan --bulk-state` | Longer if DerivedData/Caches are huge |

If **micro** is slow, something is wrong with the machine or Python env — not
normal.

### Findings look scary but score is OK

Info and some warns are educational. Read the recommendation line.  
**Critical** on backup/drive/headroom deserves action the same day.

### `state.growth` used to scream nonsense numbers

Growth warnings need **several full scans over days** and a sanity cap.
A brand-new install should **not** claim “29 GB/day.” If it does after a
fresh install, open an issue — that’s a bug.

### Clean does nothing / “nothing found”

Target paths may not exist on your machine (e.g. no Windsurf). That’s fine.

### Clean skipped because app is running

```sh
# Quit the app from the menu bar (Cmd+Q), then:
wtfssd clean cursor-caches --apply

# Nuclear override (only if you understand risk):
wtfssd clean cursor-caches --apply --force
```

### I cleaned and free space barely moved

Common causes:

1. Files still in **Trash** — empty Trash  
2. **APFS snapshots** holding blocks — Time Machine local snapshots  
3. You cleaned a small target; the hog is Xcode/Docker — try  
   `wtfssd scan --bulk-state` and `wtfssd optimize headroom`  
4. Active swap / other apps writing while you look  

### Notifications never appear

- `watch --once` must actually run (agent installed and loaded)  
- Findings may be **info** only (never notify)  
- Or still inside **cooldown** (same warn within 24h)  
- macOS may be suppressing alerts for Terminal/osascript — check  
  System Settings → Notifications  

Check agent:

```sh
launchctl list | grep wtfssd
ls ~/Library/LaunchAgents/com.wtfssd*
```

Reload:

```sh
wtfssd optimize uninstall-agent
wtfssd optimize install-agent
```

### “Permission denied” or odd OSError lines

Some system paths are unreadable without admin. Collectors are built to
**degrade** (mark unavailable), not crash. Report the section that failed.

### I used to have a menu bar app

It’s **unmaintained**. Don’t install `menubar/`. Use Terminal + optional
LaunchAgent. See `menubar/UNMAINTAINED.md`.

### Python errors / “internal error”

```sh
python3 --version    # need 3.10+
cd /path/to/wtfssd
python3 -m wtfssd scan
```

If it still blows up, copy the full error. Run tests if you’re developing:

```sh
python3 -m unittest discover -s tests -v
```

---

## 15. FAQ

**Q: Will this wear out my SSD by scanning?**  
A: A full scan a few times a day is noise compared to agentic IDEs. That’s why
we avoided an always-on heavy menu bar. Hourly agent is optional.

**Q: Do I need to understand SMART?**  
A: Only two ideas: **PASSED** + low **% used** → drive is fine. High % used
or media errors → back up and investigate hardware.

**Q: Is free space “15%” a hard law?**  
A: It’s an operational floor from real Mac behavior, not physics. Below ~10%
things get ugly fast.

**Q: Can I run this every minute in a loop?**  
A: You *can* (`watch --interval 1 --micro`), but don’t. Use on-demand or
hourly full.

**Q: Does clean remove my projects / source code?**  
A: Not by design. Targets are caches, derived data, tool state. Protected
paths (Documents, Desktop, … — matched case-insensitively) and paths
outside your home are denied. Symlinks are refused, not followed.

**Q: Secrets scanner?**  
A: Off by default. Enable only if you want path/line/rule hits in agent state
files — it never prints the secret values.

**Q: Why won’t you use sudo for “complete” checks?**  
A: So every scan stays password-free, safe, and light. Root-only signals
(swapfile listing, continuous SMC temps, system-wide fs_usage) are listed in
[§11](#11-how-thorough-is-a-scan-coverage--no-sudo). Run those tools yourself
if you need them; wtfssd covers the article’s failure modes without root.

**Q: What’s the most thorough scan I can run?**  
A: `brew install smartmontools`, optional config for `git.repos` /
`smart.external_devices` / `secrets.enabled`, then  
`wtfssd scan --bulk-state`.

**Q: Where is the long command list?**  
A: **[COMMANDS.md](../COMMANDS.md)**.

---

## 16. Safety rules (read once)

1. `clean` without `--apply` **cannot** delete.  
2. Prefer Trash over `--hard`.  
3. Quit owning apps before cleaning their state.  
4. `cursor-vscdb` deletes **local chat history** — intentional high risk.  
5. Keep Time Machine (or other backups) for real data — this tool is not a backup.  
6. Read the finding recommendation before doing something heroic.

---

## 17. Where files live

| Path | What |
|------|------|
| `~/.config/wtfssd/config.json` | Your settings overrides |
| `~/.local/share/wtfssd/history.jsonl` | Past scan snapshots |
| `~/.local/share/wtfssd/metrics.db` | Metric time series |
| `~/.local/share/wtfssd/alert_state.json` | Notification cooldowns |
| `~/.local/share/wtfssd/backups/` | Copies of high-risk files before clean |
| `~/Library/LaunchAgents/com.wtfssd.watch.plist` | Optional hourly agent |

---

## 18. Docs map & license

| Document | Who it’s for |
|----------|----------------|
| [README.md](../README.md) | The front page: install, quickstart, feature map |
| **This manual** | Humans: why, first hour, how to read results, troubleshooting |
| **[COMMANDS.md](../COMMANDS.md)** | Humans: every workflow + every flag + clean targets |
| **[AGENTS.md](../AGENTS.md)** | AI/coding agents working **in** this repository |
| [`superpowers/specs/`](superpowers/specs/) | Design specs (resource-ethical v2 = current product rules) |

### Tests (developers)

```sh
python3 -m unittest discover -s tests -v
```

### License

MIT
