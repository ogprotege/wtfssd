# Resource-Ethical v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make wtfssd quieter than the problems it finds: a rich on-demand forensic CLI, one optional background path, true micro/fast/full tiers, trustworthy growth alerts, and a menu bar that does not re-spawn multi-second Python scans every minute.

**Architecture:** Keep the Python collector engine and safety model. Fix continuous presence by (1) allow-list tiers instead of “skip slow list,” (2) split state walks into AI-core vs weekly bulk, (3) gate derived findings until baselines mature, (4) stop stacking menubar + dual LaunchAgents, (5) make the menubar poll a true micro path (or a cached status file). Do not add collectors, token accounting, or sudo monitors in this plan.

**Tech Stack:** Python ≥ 3.10 standard library only; Swift 6 / SwiftUI menubar (no deps); stdlib `unittest`; macOS launchd.

**Source review:** Session plan “Honest product & architecture review: wtfssd” (2026-08-02). Live timings on this machine: writerate ~1.0s, statedirs ~1.45s, “fast” scan ~1.3s, full ~4.9s; menubar alone ≈ 38 min wall-scan/day at current defaults.

## Global Constraints

- Python package: **stdlib only**. No pip deps. No `shell=True`. Commands only via `collectors._run.run_cmd`.
- Collectors **never raise**; degrade with `available=False` / empty + note.
- **No sudo.** Never add write-latency probes or powermetrics.
- Clean safety model is **frozen**: dry-run default, Trash, app guards, backup-first vscdb, denylist.
- `models.py` fields: additive only if a task explicitly requires a new field; prefer config + analyze changes first.
- Project root: `/Users/biscuit/wtfssd`. Branch: create `resource-ethical-v2` from current `rename-wtfssd` (or main after merge) before Task 1 code.
- Run **only the named test module** while developing a task; full suite once per stage.
- Line endings LF; `from __future__ import annotations` on new/edited Python modules.
- Do **not** implement token/cost tracking, multi-device sync, or new domains in this plan.
- Package name is `wtfssd` (console script `wtfssd`). Ignore any leftover `ssdwtf` under `build/`.

---

## Outcome checklist (definition of done)

When every stage below is complete, all of the following must be true:

- [x] `wtfssd scan --micro` finishes in **&lt; 100 ms** wall time on a warm machine (no iostat, no smartctl, no `du` walks). — **0.09 s** (2026-08-02)
- [x] `wtfssd scan --fast` finishes in **&lt; 500 ms** typical (no writerate, no statedirs walk). — **0.21 s** (2026-08-02)
- [ ] `wtfssd scan` (full) still runs forensic collectors; AI-core statedirs every full scan; **bulk** statedirs only when `--bulk-state` or daily policy.
- [ ] Menubar default refresh is **≥ 5 min** and uses **micro** (or status-file) path — not full `--fast` with iostat.
- [ ] `optimize install-agent` installs **at most one** continuous agent by default (hourly full **or** menubar-owned; no dual 5‑min + hourly stack as default).
- [x] `state.growth` does not fire until **≥ 3 calendar days** of comparable full statedirs samples exist and rate is within a sanity cap. — verified live 2026-08-02
- [ ] Full suite green: `python3 -m unittest discover -s tests -v`
- [ ] README + AGENTS.md describe micro/fast/full and the “one scheduler” rule.
- [ ] Live self-check: with menubar running at defaults, Activity Monitor does not show a Python process every 60s for ~1+ second.

---

## File map (what will change)

| File | Role in this plan |
|---|---|
| `wtfssd/config.py` | New defaults: `tiers.micro`, rewrite `tiers.fast`/`slow`, growth gates, agent mode, bulk-state flags |
| `wtfssd/cli.py` | `build_report` allow-list tiers; `--micro`; install-agent modes; optional `--bulk-state` |
| `wtfssd/collectors/statedirs.py` | Split AI-core vs bulk path lists; optional bulk collection |
| `wtfssd/history.py` | Mature baseline gates for `state_growth_gb_per_day` |
| `wtfssd/analyze.py` | Use gated growth; optional confidence/evidence wording |
| `wtfssd/optimize.py` | Default single agent; optional fast agent only with explicit flag |
| `menubar/.../main.swift` | Defaults, full-scan interval, scheduler exclusivity notes |
| `menubar/.../Scanner.swift` | Call `--micro` for title ticks; full on longer timer / open |
| `menubar/.../PopoverView.swift` / `DetailViews.swift` | Refresh picker defaults (5m / 15m / 30m) |
| `tests/test_cli.py`, `test_config.py`, `test_history.py`, `test_analyze.py`, `test_statedirs.py`, `test_optimize.py` | Tier + growth + agent tests |
| `README.md`, `AGENTS.md`, design spec patch | Document resource-ethical posture |
| `docs/superpowers/specs/2026-08-02-resource-ethical-v2.md` | Short companion spec (Stage A) |

---

## Stage map (do in order)

| Stage | Name | Why this order | Can do together? | Status |
|---|---|---|---|---|
| **0** | Machine relief (ops only) | Stop the bleeding on *this* Mac before code | **Yes — first session** | **DONE 2026-08-02** |
| **A** | Spec stub + branch | Lock decisions before code thrash | Yes (short) | **DONE 2026-08-02** |
| **1** | True tier allow-lists | Unblocks every later continuous path | Code session 1 | **DONE 2026-08-02** |
| **2** | Growth trust gates | Stops false panic findings | Code session 2 | **DONE 2026-08-02** |
| **3** | State registry split | Removes expensive walks from default full | Code session 3 | pending |
| **4** | Single-scheduler agents | Stops dual LaunchAgent stack | Code session 4 |
| **5** | Menubar micro path | Makes UI ethical by default | Code session 5 |
| **6** | Docs + verification | Ship confidence | Final session |
| **7** | Optional: status-file daemon | Only if micro-from-Swift is still not enough | Later / optional |

**Dependency graph:**

```
0 ──► A ──► 1 ──► 2
              │
              ├──► 3 ──► 5
              │
              └──► 4 ──► 5 ──► 6
                              └──► 7 (optional)
```

Stage 2 can parallel Stage 3/4 after Stage 1 lands. Stage 5 needs Stages 1 and 4.

---

# STAGE 0 — Machine relief (ops only, no product code)

> **STATUS: COMPLETED 2026-08-02** (session with user)  
> **presence = A (CLI only)** — locked for resource-ethical v2 development  
> See completion log at end of this stage.

**Goal:** Immediately stop stacked continuous monitoring on the development machine so you feel the difference before any PR.

**Why first:** Code fixes do not help if three pollers are already installed and the menubar is ticking every 60s.

### Task 0.1: Inventory what is running

- [x] **Step 1: List LaunchAgents**

```bash
ls -la ~/Library/LaunchAgents/com.wtfssd* 2>/dev/null || true
ls -la ~/Library/LaunchAgents/com.ssdwtf* 2>/dev/null || true
launchctl list | grep -E 'wtfssd|ssdwtf' || true
```

**Result (2026-08-02):** No `com.wtfssd.*` or `com.ssdwtf.*` plists. No agents in `launchctl list`.  
(Earlier install left only a stale `~/.local/share/wtfssd/watch-fast.log` — 46 bytes, last line from a prior `watch --once --fast`.)

- [x] **Step 2: List menu bar / Python scan processes**

```bash
ps aux | grep -E 'wtfssd-menubar|WTFSSDMonitor|python3 -m wtfssd|wtfssd scan' | grep -v grep || true
```

**Result:** No menubar, no `python3 -m wtfssd`, no scan processes.

- [x] **Step 3: Note timings baseline (before relief)**

```bash
cd /Users/biscuit/wtfssd
/usr/bin/time -p python3 -m wtfssd scan --fast --no-history >/dev/null
/usr/bin/time -p python3 -m wtfssd scan --no-history >/dev/null
```

**Baseline timings (2026-08-02, warm, on-demand only):**

| Command | real | user | sys |
|---------|------|------|-----|
| `scan --fast --no-history` | **1.26 s** | 0.09 | 0.12 |
| `scan --no-history` (full) | **5.10 s** | 0.59 | 1.78 |

(Matches review: writerate ~1 s floor on “fast”; statedirs walk dominates full.)

### Task 0.2: Choose ONE continuous presence (decision)

Pick **exactly one** for the machine while v2 is developed:

| Option | When to choose | Action |
|---|---|---|
| **A. CLI only** | You only need on-demand `scan` / `clean` | Unload all agents + quit menubar |
| **B. Menubar only** | You want a glanceable grade | Keep menubar; unload all LaunchAgents; set refresh to 5 min in Settings |
| **C. Hourly agent only** | Headless machine, no menubar | Keep `com.wtfssd.watch` only; quit menubar; remove fast agent |

**Recommended for development of this plan: Option A or B.** Option C is fine after Stage 4.

- [x] **Step 1: Write the choice down** (one line in `WIP.md` under a “Resource-ethical v2” heading): `presence = A|B|C`

**Decision: `presence = A` (CLI only).**  
Rationale: agents and menubar were already off; development of Stages A–6 should stay on-demand so we do not re-stack pollers while changing tiers. Revisit B after Stage 5 (micro menubar) ships.

### Task 0.3: Unload stacked agents

- [x] **Step 1: Bootout and remove plists (safe even if missing)**

```bash
uid=$(id -u)
for label in com.wtfssd.watch.fast com.wtfssd.watch com.ssdwtf.watch.fast com.ssdwtf.watch; do
  launchctl bootout "gui/${uid}/${label}" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/${label}.plist"
done
launchctl list | grep -E 'wtfssd|ssdwtf' || echo "no wtfssd agents loaded"
```

**Result:** Idempotent cleanup run. Confirmed: no agents loaded, no plists.

- [x] **Step 2: If presence = A or C, quit the menubar**

**Result:** Menubar was not running; nothing to quit. (App may still exist at `menubar/build/WTFSSDMonitor.app` — do not open during v2 until Stage 5.)

- [x] **Step 3: If presence = B, open Settings…** — N/A (chose A).

### Task 0.4: Smoke that the CLI still works

- [x] **Step 1: One full forensic scan (on demand is fine)**

```bash
cd /Users/biscuit/wtfssd
python3 -m wtfssd scan --no-history
```

**Result:** Scan succeeded. Headline live findings (forensics still useful without daemons):

- Health **68/100 (C)**
- Disk: **47% free** (460 GB of 995 GB) — headroom OK
- Swap: **0 GB**
- **54** IDE-related processes (warn)
- Agentic state **~20.2 GB** total (warn) — Claude AS 13.5 GB, Cursor path not top-line this run, codex-home 2.3 GB, user-caches 3.4 GB
- **state.growth ~29.4 GB/day** (warn, evidence: derived) — known false-positive class; Stage 2 fixes
- Backup destination not mounted (warn)
- SMART: **1% used**, 15.0 TB written / 254 h (info)
- Retention missing for claude-code, claude-desktop, cursor (info)

- [x] **Step 2: Confirm no background scan churn**

```bash
ps aux | grep -E 'python3 -m wtfssd|wtfssd scan' | grep -v grep || echo "quiet — good"
```

**Result:** `quiet — good` (no background scan processes after on-demand run finished).

**Stage 0 done when:** agents are not stacked, presence choice is written, CLI scan works, machine feels quieter.

### Stage 0 completion log

| Field | Value |
|-------|--------|
| Completed | 2026-08-02 |
| Session | User + agent, Stage 0 together |
| presence | **A (CLI only)** |
| Agents before | None loaded (already clean) |
| Agents after | None loaded; bootout/rm verified |
| Menubar | Not running; leave closed until Stage 5 |
| Baseline fast | 1.26 s real |
| Baseline full | 5.10 s real |
| Data preserved | `~/.local/share/wtfssd/` (history.jsonl 62 lines, metrics.db, etc.) untouched |
| Product code | **None changed** (ops only) |
| Next stage | **Stage A** — companion spec + branch `resource-ethical-v2` |

**Do not** run `optimize install-agent` or open the menubar app until the matching stage lands (4 / 5), or you re-create the stacked continuous load this stage removed.

---

# STAGE A — Spec stub + branch

> **STATUS: COMPLETED 2026-08-02** (subagent-driven)  
> Commit: `3b5be6f` docs: resource-ethical v2 spec (tiers, one scheduler, growth gates)  
> Branch: `resource-ethical-v2`

**Goal:** Capture the resource-ethical decisions in-repo so implementers do not re-debate them mid-PR.

### Task A.1: Write the companion spec

- [x] **Step 1: Create** `docs/superpowers/specs/2026-08-02-resource-ethical-v2.md` with this exact content:

```markdown
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
```

- [x] **Step 2: Commit** — done (`3b5be6f`; also included plan file).

### Stage A completion log

| Field | Value |
|-------|--------|
| Completed | 2026-08-02 |
| Mode | Subagent-driven (Task A.1) |
| Branch | `resource-ethical-v2` |
| Commit | `3b5be6f` |
| Artifacts | `docs/superpowers/specs/2026-08-02-resource-ethical-v2.md`, plan committed |
| Next | Stage 1 |

---

# STAGE 1 — True tier allow-lists

> **STATUS: COMPLETED 2026-08-02** (subagent-driven)  
> Commits: `96f0a1b` config allow-lists; `0983bdc` cli tiers + `--micro`  
> Live timings after Stage 1: **micro 0.09–0.11 s**, **fast 0.21–0.24 s** (was 1.26 s)

**Goal:** Make `--micro` and `--fast` mean “only these collectors,” so continuous UI has a real cheap path. **This is the first code stage to implement together after Stage 0.**

### Task 1.1: Config defaults for three allow-lists

**Files:**
- Modify: `wtfssd/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `DEFAULTS["tiers"]` keys `micro`, `fast`, `full` (lists of collector names). Keep `slow` temporarily as deprecated unused, or remove after cli switch — prefer **replace** with the three lists only.

- [x] **Step 1: Write failing test** — append to `tests/test_config.py`:

```python
    def test_tiers_are_allowlists(self):
        cfg, warn = config.load_config(path=Path("/nonexistent/wtfssd-config.json"))
        self.assertIsNone(warn)
        tiers = cfg["tiers"]
        self.assertIn("micro", tiers)
        self.assertIn("fast", tiers)
        self.assertIn("full", tiers)
        self.assertIn("swap", tiers["micro"])
        self.assertIn("disk", tiers["micro"])
        self.assertNotIn("writerate", tiers["micro"])
        self.assertNotIn("writerate", tiers["fast"])
        self.assertIn("writerate", tiers["full"])
        self.assertNotIn("statedirs", tiers["fast"])
        self.assertIn("statedirs", tiers["full"])
```

- [x] **Step 2: Run test — expect FAIL** (TDD RED confirmed by implementer)

- [x] **Step 3: Update `DEFAULTS["tiers"]` in `wtfssd/config.py`**

Replace the existing `"tiers": {...}` entry with:

```python
    "tiers": {
        # Allow-lists. build_report only runs collectors named for the active tier.
        "micro": ["swap", "disk", "processes", "pressure"],
        "fast": [
            "swap", "disk", "processes", "pressure",
            "smart", "system", "backup", "retention",
            "launchd", "spotlight", "mcp",
        ],
        "full": [
            "swap", "disk", "processes", "pressure",
            "smart", "system", "backup", "retention",
            "launchd", "spotlight", "mcp",
            "statedirs", "apfs", "crashes", "churn",
            "fds", "secrets", "logs", "gitwatch", "writerate",
            # external_smart follows config smart.external_devices; always
            # attempted in full when the list is non-empty (see cli).
        ],
    },
```

Also extend `state` defaults (used in Stage 2; safe to add now):

```python
    "state": {
        "vscdb_warn_gb": 2.0,
        "growth_warn_gb_day": 1.0,
        "total_warn_gb": 20.0,
        "growth_min_samples": 4,
        "growth_min_days": 3.0,
        "growth_max_gb_day": 50.0,
        "include_bulk_default": False,
    },
```

And `watch` defaults:

```python
    "watch": {
        "interval_minutes": 60,
        "fast_interval_minutes": 15,
        "agent_mode": "hourly",  # hourly | fast | both | none
    },
```

- [x] **Step 4: Run test — expect PASS** — `tests.test_config` 5/5 OK

- [x] **Step 5: Commit** — `96f0a1b` config: allow-list tiers micro/fast/full; growth/agent defaults

### Task 1.2: Rewrite `build_report` to honor allow-lists

**Files:**
- Modify: `wtfssd/cli.py` (`build_report`, argparse for scan/watch)
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `build_report(config, tier: str = "full") -> HealthReport` where `tier` is `"micro" | "fast" | "full"`.
- Back-compat: `build_report(config, fast=True)` still works → treat as `tier="fast"`. Prefer new signature:

```python
def build_report(config: dict, *, tier: str = "full",
                 bulk_state: bool = False) -> HealthReport:
```

If both old and new call sites exist, support:

```python
def build_report(config: dict, fast: bool = False, *,
                 tier: str | None = None,
                 bulk_state: bool = False) -> HealthReport:
    if tier is None:
        tier = "fast" if fast else "full"
```

- [x] **Step 1: Write failing tests** in `tests/test_cli.py` (adapt to existing mock style; the file already patches collectors):

```python
    def test_build_report_micro_skips_writerate_and_statedirs(self):
        # Patch every collect_* to raise if called unexpectedly is heavy;
        # instead spy call counts via wrappers.
        calls: list[str] = []

        def wrap(name, orig):
            def _inner(*a, **k):
                calls.append(name)
                return orig(*a, **k) if callable(orig) else orig
            return _inner

        # Prefer: patch writerate and statedirs to set a flag if invoked.
        ...
```

**Practical test approach (use this exact version if the above is too coupled):**

```python
    def test_build_report_micro_does_not_call_writerate(self):
        config, _ = config_mod.load_config(path=Path("/nonexistent"))
        called = {"writerate": False, "statedirs": False}

        def wr(*a, **k):
            called["writerate"] = True
            return models.WriteRateReport(available=False, error="spy")

        def sd(*a, **k):
            called["statedirs"] = True
            return models.StateDirReport(note="spy")

        with mock.patch.object(cli.writerate_col, "collect_writerate", wr), \
             mock.patch.object(cli.statedirs_col, "collect_statedirs", sd), \
             mock.patch.object(cli.swap_col, "collect_swap",
                 return_value=models.SwapReport(0, 0, 0)), \
             mock.patch.object(cli.disk_col, "collect_disk",
                 return_value=models.DiskReport("/", 100, 50, 50, 50, 50)), \
             mock.patch.object(cli.proc_col, "collect_processes",
                 return_value=models.ProcessReport([], 0)), \
             mock.patch.object(cli.pressure_col, "collect_pressure",
                 return_value=models.PressureReport(available=True, level=1)):
            cli.build_report(config, tier="micro")
        self.assertFalse(called["writerate"])
        self.assertFalse(called["statedirs"])

    def test_build_report_fast_does_not_call_writerate(self):
        # same pattern: writerate and statedirs must not be called for tier=fast
        ...
```

Fill the second test the same way, patching the remaining always-on collectors that `fast` still needs (`smart`, `system`, etc.) with minimal empty reports so the function does not call real subprocesses.

- [x] **Step 2: Run tests — expect FAIL** (old build_report always calls writerate) — TDD RED confirmed

- [x] **Step 3: Implement allow-list `build_report`**

Core logic (place at top of `build_report` body):

```python
def build_report(config: dict, fast: bool = False, *,
                 tier: str | None = None,
                 bulk_state: bool = False) -> HealthReport:
    if tier is None:
        tier = "fast" if fast else "full"
    if tier not in ("micro", "fast", "full"):
        tier = "full"
    allowed = set(config.get("tiers", {}).get(tier, []))

    def want(name: str) -> bool:
        return name in allowed

    # For every collector field:
    #   if want("swap"): collect else placeholder report with note/error
    # external_smart: only if want("smart") or tier == "full" and devices configured
    # statedirs: if want("statedirs"): collect_statedirs(bulk=bulk_state or config...)
    # writerate: only if want("writerate")
```

Placeholder pattern already used for `--fast` — extend it:

```python
statedirs=(statedirs_col.collect_statedirs(...) if want("statedirs")
           else StateDirReport(note="not collected (--micro/--fast)")),
writerate=(writerate_col.collect_writerate(...) if want("writerate")
           else WriteRateReport(available=False,
                                error=f"not collected (tier={tier})")),
```

Apply `want(...)` to **every** collector that is currently unconditional (`retention`, `launchd`, `spotlight`, `mcp`, `system`, `smart`, `pressure`, `backup`, etc.). That is the main bugfix: today several always run even under `--fast`.

- [x] **Step 4: Wire CLI flags**

On the `scan` and `watch` subparsers:

```python
p.add_argument("--micro", action="store_true",
               help="micro tier only (menu-bar safe: swap/disk/pressure/processes)")
p.add_argument("--fast", action="store_true",
               help="fast tier (no statedirs/writerate/forensics)")
```

In `cmd_scan` / `_run_scan` / `cmd_watch`:

```python
if getattr(args, "micro", False):
    tier = "micro"
elif getattr(args, "fast", False):
    tier = "fast"
else:
    tier = "full"
# mutual exclusion: if both --micro and --fast, prefer micro and print warning
```

- [x] **Step 5: Run module tests** — `tests.test_cli` + `tests.test_config` OK; full suite **214 OK**

- [x] **Step 6: Live timing gate**

| Command | real (controller recheck) | vs Stage 0 baseline |
|---------|---------------------------|---------------------|
| `scan --micro --no-history` | **0.09 s** | n/a (new) |
| `scan --fast --no-history` | **0.21 s** | was **1.26 s** |
| full (unchanged path) | ~5 s | was 5.10 s |

writerate/statedirs: `available=False` / note `not collected (tier=micro|fast)` on micro/fast payloads.

- [x] **Step 7: Commit** — `0983bdc` cli: allow-list tiers; --micro; writerate only on full

**Stage 1 done when:** live `--micro` is clearly faster than current `--fast`, and writerate is not invoked on micro/fast. **MET.**

### Stage 1 completion log

| Field | Value |
|-------|--------|
| Completed | 2026-08-02 |
| Mode | Subagent-driven (Tasks 1.1, 1.2) |
| Commits | `96f0a1b` config; `0983bdc` cli |
| Tests | 214 full suite OK; 14 focused cli+config OK |
| micro wall | 0.09–0.11 s |
| fast wall | 0.21–0.24 s |
| Notes | `bulk_state` accepted on `build_report` but unused until Stage 3 |
| Next | **Stage 2** — growth trust gates |

---

# STAGE 2 — Growth trust gates

> **STATUS: COMPLETED 2026-08-02** (subagent-driven)  
> Commit: `3dd4325` history: gate state.growth on samples, span, and sanity cap  
> Live: **no `state.growth` finding** on current history (was ~29 GB/day false positive)  
> Suite: **217 OK**

**Goal:** Stop absurd `state.growth ~29 GB/day` false positives until enough comparable samples exist.

### Task 2.1: Gate `state_growth_gb_per_day`

**Files:**
- Modify: `wtfssd/history.py`
- Modify: `wtfssd/analyze.py` (pass config thresholds if needed)
- Test: `tests/test_history.py`, `tests/test_analyze.py`

**Interfaces:**
- Change signature to:

```python
def state_growth_gb_per_day(
    history: list[HealthReport],
    window_days: float = 14.0,
    *,
    min_samples: int = 4,
    min_span_days: float = 3.0,
    max_gb_day: float | None = 50.0,
) -> float | None:
```

Return `None` (no finding) when:
1. fewer than `min_samples` usable rows (statedirs.note empty, total collected),
2. span between first and last usable timestamp &lt; `min_span_days`,
3. computed rate &gt; `max_gb_day` when `max_gb_day is not None` (treat as baseline discontinuity — return None rather than fire warn).

- [ ] **Step 1: Extend `tests/test_history.py`**

```python
    def test_state_growth_requires_min_span(self):
        # two samples 1 hour apart, large delta → None (not enough span)
        ...
        self.assertIsNone(history.state_growth_gb_per_day(
            h, min_samples=2, min_span_days=3.0))

    def test_state_growth_requires_min_samples(self):
        # 3 samples over 5 days → None if min_samples=4
        ...

    def test_state_growth_caps_absurd_rate(self):
        # 100 GB jump over 3 days → None when max_gb_day=50
        ...
```

Build `HealthReport` stubs the same way existing tests do (see current `test_state_growth_rate`).

- [ ] **Step 2: Run — expect FAIL**

```bash
python3 -m unittest tests.test_history -v
```

- [ ] **Step 3: Implement gates in `history.state_growth_gb_per_day`**

After building `recent`:

```python
    if len(recent) < min_samples:
        return None
    days = _window_days(recent[0], recent[-1])
    if not days or days < min_span_days:
        return None
    delta = recent[-1].statedirs.total_bytes - recent[0].statedirs.total_bytes
    rate = delta / 1e9 / days
    if max_gb_day is not None and rate > max_gb_day:
        return None
    return rate
```

- [ ] **Step 4: Wire config in `analyze.py`**

Where growth is computed:

```python
    st_cfg = config.get("state", {})
    growth = state_growth_gb_per_day(
        history,
        min_samples=int(st_cfg.get("growth_min_samples", 4)),
        min_span_days=float(st_cfg.get("growth_min_days", 3.0)),
        max_gb_day=float(st_cfg.get("growth_max_gb_day", 50.0)),
    )
```

- [ ] **Step 5: Run tests**

```bash
python3 -m unittest tests.test_history tests.test_analyze -v
```

- [ ] **Step 6: Live check**

```bash
python3 -m wtfssd scan --no-history 2>/dev/null | grep -i growth || echo "no growth finding (good if baseline young)"
```

- [ ] **Step 7: Commit**

```bash
git add wtfssd/history.py wtfssd/analyze.py tests/test_history.py tests/test_analyze.py
git commit -m "history: gate state.growth on samples, span, and sanity cap"
```

**Stage 2 done when:** a young metrics/history DB does not emit multi-ten-GB/day growth warns.

---

# STAGE 3 — State registry split (AI-core vs bulk)

**Goal:** Full scans still measure agentic state cheaply; expensive walks of Caches/Docker/Xcode/HF become opt-in bulk.

### Task 3.1: Split `STATE_DIRS` and collect API

**Files:**
- Modify: `wtfssd/collectors/statedirs.py`
- Test: `tests/test_statedirs.py`

**Interfaces:**
- Produces:

```python
AI_STATE_DIRS: tuple[...]   # cursor, claude, codex, windsurf, zed, vscdb, etc.
BULK_STATE_DIRS: tuple[...] # xcode, docker, huggingface, lmstudio, ollama, user-caches, jetbrains models

def collect_statedirs(
    home: Path | None = None,
    *,
    include_bulk: bool = False,
) -> StateDirReport:
```

Default `include_bulk=False`.

**AI-core keys (keep on every full scan):**
- `cursor-app-support`, `cursor-home`, `cursor-vscdb`, `cursor-vscdb-backups`
- `claude-app-support`, `claude-home`
- `code-app-support`, `windsurf-app-support`, `zed-app-support`, `codex-home`

**Bulk keys (only with include_bulk):**
- `jetbrains-app-support`, `ollama-models`, `lmstudio-cache`, `huggingface-cache`, `mlx-cache`, `docker-data`, `xcode-deriveddata`, `user-caches`

- [ ] **Step 1: Write tests** for size of registry and bulk flag:

```python
    def test_default_collect_skips_bulk_keys(self):
        # use a TemporaryDirectory as home with fake AI + bulk dirs
        ...
        rep = statedirs.collect_statedirs(home=home, include_bulk=False)
        keys = {d.key for d in rep.dirs}
        self.assertIn("cursor-home", keys)
        self.assertNotIn("user-caches", keys)

    def test_bulk_collect_includes_caches(self):
        ...
        rep = statedirs.collect_statedirs(home=home, include_bulk=True)
        keys = {d.key for d in rep.dirs}
        self.assertIn("user-caches", keys)
```

- [ ] **Step 2: Implement split + loop over AI only or AI+bulk**

- [ ] **Step 3: Wire `cli.build_report`**

```python
include_bulk = bulk_state or bool(
    config.get("state", {}).get("include_bulk_default", False))
statedirs=(statedirs_col.collect_statedirs(include_bulk=include_bulk)
           if want("statedirs") else StateDirReport(...))
```

- [ ] **Step 4: CLI flag on scan**

```python
p.add_argument("--bulk-state", action="store_true",
               help="include Xcode/Docker/Caches/model dirs in statedirs (slow)")
```

- [ ] **Step 5: Timing comparison**

```bash
/usr/bin/time -p python3 -m wtfssd scan --no-history >/dev/null
/usr/bin/time -p python3 -m wtfssd scan --bulk-state --no-history >/dev/null
```

Expected: default full faster than bulk; default still reports Cursor/Claude/Codex sizes.

- [ ] **Step 6: Commit**

```bash
git add wtfssd/collectors/statedirs.py wtfssd/cli.py tests/test_statedirs.py
git commit -m "statedirs: AI-core by default; bulk paths behind --bulk-state"
```

### Task 3.2: Headroom / clean still see bulk when needed

**Files:**
- Modify: `wtfssd/cli.py` `cmd_optimize` headroom path (currently calls `collect_statedirs()` for top consumers)
- Modify: `wtfssd/cleaners.py` only if it depends on full registry for sizing — check first.

- [ ] **Step 1: In `optimize headroom`, call `collect_statedirs(include_bulk=True)`** so “what is eating space” remains honest when the user asks.

- [ ] **Step 2: Run** `python3 -m wtfssd optimize headroom` and confirm large consumers can still appear.

- [ ] **Step 3: Commit** if code changed.

**Stage 3 done when:** default full scan no longer walks `Library/Caches` / Docker / HF; headroom still can.

---

# STAGE 4 — Single-scheduler LaunchAgents

**Goal:** `install-agent` no longer silently installs two pollers.

### Task 4.1: Agent mode in optimize + CLI

**Files:**
- Modify: `wtfssd/optimize.py` (optional helper `install_agents(mode=...)`)
- Modify: `wtfssd/cli.py` `cmd_optimize` install-agent / uninstall-agent
- Test: `tests/test_optimize.py`

**Interfaces:**
- Produces:

```python
def install_agents(
    mode: str = "hourly",
    *,
    interval_seconds: int = 3600,
    fast_interval_seconds: int = 900,
    launch_agents_dir: Path | None = None,
) -> list[tuple[Path, bool]]:
    """mode: hourly | fast | both | none"""
```

- [ ] **Step 1: Tests**

```python
    def test_install_hourly_only_by_default(self):
        with TemporaryDirectory() as td:
            paths = optimize.install_agents("hourly", launch_agents_dir=Path(td))
            names = {p.name for p, _ in paths}
            self.assertEqual(names, {"com.wtfssd.watch.plist"})

    def test_install_both_writes_two(self):
        ...
            self.assertEqual(len(paths), 2)

    def test_install_none_writes_zero(self):
        ...
            self.assertEqual(paths, [])
```

- [ ] **Step 2: Implement `install_agents`** using existing `install_agent` / `install_fast_agent`. For `mode=="both"`, print warning string returned to CLI:

```python
WARN_BOTH = (
    "warning: agent_mode=both stacks two pollers; prefer hourly OR menubar, "
    "not both (see resource-ethical v2 spec)"
)
```

- [ ] **Step 3: Change `cmd_optimize` install-agent**

```python
    mode = config.get("watch", {}).get("agent_mode", "hourly")
    # allow CLI override later: --mode both
    results = optimize.install_agents(mode, ...)
    if mode == "both":
        print(WARN_BOTH)
    if mode == "none":
        print("agent_mode=none: nothing installed; use menubar or run scan manually")
        return 0
```

- [ ] **Step 4: `uninstall-agent` continues to remove both labels** (already does) — keep that.

- [ ] **Step 5: Commit**

```bash
git add wtfssd/optimize.py wtfssd/cli.py tests/test_optimize.py
git commit -m "optimize: default single LaunchAgent (hourly); both is opt-in"
```

### Task 4.2: Operator docs in command help

- [ ] **Step 1: Update install-agent help text** to say default is hourly full only; menubar users should uninstall agents.

- [ ] **Step 2: Commit** with Stage 6 if bundled with README.

**Stage 4 done when:** a fresh `install-agent` creates one plist unless mode is both.

---

# STAGE 5 — Menubar micro path

**Goal:** Title refresh no longer runs 1s iostat Python scans every minute.

### Task 5.1: Scanner calls `--micro` for fast path

**Files:**
- Modify: `menubar/Sources/wtfssd-menubar/Scanner.swift`
- Modify: `menubar/Sources/wtfssd-menubar/main.swift`
- Modify: `menubar/Sources/wtfssd-menubar/PopoverView.swift` / `DetailViews.swift`

**Interfaces:**
- `scan(tier: Tier)` where `enum Tier { case micro, fast, full }`
- Micro args: `["scan", "--micro", "--json", "--no-history"]`
- Full args: `["scan", "--json", "--no-history"]` (AI-core statedirs; no bulk)
- Optional bulk only from a future menu action — not on timer

- [ ] **Step 1: Change `Scanner.scan`**

```swift
enum ScanTier {
    case micro, full
    var args: [String] {
        switch self {
        case .micro: return ["scan", "--micro", "--json", "--no-history"]
        case .full:  return ["scan", "--json", "--no-history"]
        }
    }
    var timeout: TimeInterval { self == .micro ? 15 : 120 }
}

func scan(tier: ScanTier) throws -> Payload {
    var args = tier.args
    ...
    let result = try run(exe, finalArgs, cwd: cwd, timeout: tier.timeout)
    // isFull: tier == .full
}
```

- [ ] **Step 2: `main.swift` timers**

```swift
private let fullRefreshInterval: TimeInterval = 3600  // was 900

// refresh() -> scanner.scan(tier: .micro)
// refreshFull() -> scanner.scan(tier: .full)
```

- [ ] **Step 3: Default refresh interval 300**

In `MonitorModel.init`:

```swift
refreshInterval = saved > 0 ? saved : 300  // was 60
```

- [ ] **Step 4: Settings picker options**

```swift
Text("5 min").tag(300.0)
Text("15 min").tag(900.0)
Text("30 min").tag(1800.0)
// remove 30s / 1min OR keep 1min as "aggressive" last option with label "1 min (heavy)"
```

Recommended: **remove 30s** entirely.

- [ ] **Step 5: Rebuild and smoke**

```bash
cd /Users/biscuit/wtfssd/menubar && ./build.sh
# quit old app, open new:
open build/WTFSSDMonitor.app
# Activity Monitor: should not see python every 60s for ~1s+
```

Debug:

```bash
# from built binary if --dump-menu still works:
./build/WTFSSDMonitor.app/Contents/MacOS/wtfssd-menubar --dump-menu
```

- [ ] **Step 6: Commit**

```bash
git add menubar/Sources/wtfssd-menubar/*.swift
git commit -m "menubar: micro tier for title; 5m default; full hourly"
```

### Task 5.2: Document menubar vs agent exclusivity in Settings footer

- [ ] **Step 1: Add secondary text in SettingsView:**

```text
If this app is open, run: wtfssd optimize uninstall-agent
(only one continuous scheduler)
```

- [ ] **Step 2: Commit**

**Stage 5 done when:** menubar default path uses `--micro` and full is ≤ hourly.

---

# STAGE 6 — Docs, suite, live verification

### Task 6.1: README + AGENTS.md

**Files:**
- Modify: `README.md` (Quick start, Menu bar, config keys)
- Modify: `AGENTS.md` (tiers, agent_mode, bulk-state, growth keys)

- [ ] **Step 1: README changes (concrete)**

Replace the `scan --fast` blurb with:

```markdown
wtfssd scan --micro            # menu-bar-safe vitals only (<100ms target)
wtfssd scan --fast             # cheap counters, no statedirs/writerate walks
wtfssd scan                    # full forensic (AI-core state dirs)
wtfssd scan --bulk-state       # also size Xcode/Docker/Caches/models (slow)
wtfssd optimize install-agent  # ONE hourly LaunchAgent by default
```

Menubar section: refresh every **5 minutes** from `scan --micro`; full detail hourly.

- [ ] **Step 2: AGENTS.md** — update tier description; remove claim that fast includes writerate/backup if no longer true; document `watch.agent_mode`.

- [ ] **Step 3: Patch monitor-expansion spec** with a one-line pointer at top:

```markdown
> **Superseded in part by** `2026-08-02-resource-ethical-v2.md` for tier
> membership and continuous sampling cadence.
```

- [ ] **Step 4: Commit**

```bash
git add README.md AGENTS.md docs/superpowers/specs/*.md
git commit -m "docs: resource-ethical v2 tiers, agents, and menubar posture"
```

### Task 6.2: Full test suite + timing report

- [ ] **Step 1: Full suite**

```bash
cd /Users/biscuit/wtfssd
python3 -m unittest discover -s tests -v
```

Expected: all OK. Fix any breakages from tier signature changes (especially `test_cli` patches).

- [ ] **Step 2: Write timing table into `WIP.md`**

```markdown
## Resource-ethical v2 timings (YYYY-MM-DD)
| Command | real s |
|---------|--------|
| scan --micro --no-history | |
| scan --fast --no-history | |
| scan --no-history | |
| scan --bulk-state --no-history | |
```

- [ ] **Step 3: Outcome checklist** at top of this plan — check every box that is true.

- [ ] **Step 4: Final commit / PR**

```bash
git status
git log --oneline main..HEAD  # or rename-wtfssd..HEAD
# open PR when ready: resource-ethical v2
```

**Stage 6 done when:** suite green, docs match behavior, outcome checklist complete.

---

# STAGE 7 — Optional later: status-file daemon (only if still needed)

**Do not start until Stages 0–6 are done and you still dislike forking Python for micro.**

**Idea:** Hourly (or 5‑min micro) LaunchAgent writes `~/.local/share/wtfssd/status.json`. Menubar only reads that file for the title (no process spawn on timer). Manual “Refresh” button runs micro once.

### Task 7.1 (optional): `wtfssd status --write` 

- [ ] Add `cmd_status` that runs micro (or fast) and writes a tiny JSON:
  `{score, grade, swap_gb, disk_free_pct, ide_procs, ts}`
- [ ] Menubar timer reads file mtime + contents; if stale &gt; 2× interval, show “stale” dimmed title
- [ ] Tests for writer; no Swift unit tests required

This stage is a separate mini-plan if needed — do not expand scope mid-flight.

---

## Suggested session plan (human + agent)

| Session | Do together | Est. time | Status |
|---|---|---|---|
| **1** | Stage 0 all tasks | ~20 min | **DONE 2026-08-02** |
| **1b** | Stage A + Stage 1 (Tasks 1.1–1.2) subagent-driven | ~15 min wall | **DONE 2026-08-02** |
| **2** | Stage 2 growth gates | ~subagent session | **DONE 2026-08-02** |
| **3** | Stage 3 state split | 1–2 h | next |
| **5** | Stage 4 | 45–90 min |
| **6** | Stage 5 rebuild menubar | 1–2 h |
| **7** | Stage 6 docs + suite + PR | 1 h |

---

## Risk register

| Risk | Mitigation |
|---|---|
| User config still has old `tiers.slow` only | deep_merge: if user overrides tiers partially, ensure code falls back to DEFAULTS keys; document `wtfssd config --show` |
| Menubar binary still points at old repo path | rebuild with `menubar/build.sh` after checkout moves |
| History growth gate hides real growth | min_days=3 is short; users with real leaks still see `state.total_large` absolute warns |
| `--micro` score looks “too green” | score may ignore missing domains; domain_statuses already use unknown — verify analyze handles empty statedirs |
| Tests assume writerate always present | update fixtures/mocks in test_cli carefully |
| Presence of both menubar + hourly agent after install | README + Settings footer + install-agent print |

---

## What we deliberately will not do in this plan

- No new collectors  
- No token/cost / token-monitor features  
- No gitwatch removal (leave collector; it stays full-tier only — optional follow-up to default-disable via empty `git.repos`)  
- No secrets default-on  
- No sudo thermal  
- No redesign of clean safety  
- No Electron rewrite of menubar  

---

## Self-review (plan author)

1. **Spec coverage:** Resource review items (micro tier, writerate out of fast, one scheduler, growth gates, bulk split, menubar cadence, docs) each map to a stage/task.  
2. **Placeholders:** None intentional; Session 1 uses concrete shell; Stage 1 includes concrete config/CLI code. Swift tests are manual rebuild checks (no XCTest harness in repo).  
3. **Order:** Ops relief before code; allow-lists before menubar; growth independent; bulk after tiers; agents before menubar exclusivity messaging.  

---

## Execution handoff

**Plan complete and saved to** `docs/superpowers/plans/2026-08-02-resource-ethical-v2.md`.

**Recommended first move together:** complete **Stage 0** (unload stacked agents, pick presence A/B/C, baseline timings) then **Stage A** (spec + branch), then start **Stage 1 Task 1.1** (config allow-lists) in the same or next session.

**Execution options when you are ready to code Stage 1+:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — stay in this chat, implement task-by-task with checkpoints  

**Which approach for Session 1?** If you only want Stage 0 ops right now, say “do Stage 0 with me” and we run the inventory/unload commands together without starting code.
