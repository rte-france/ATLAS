# Profiling

## Core principle

**Never go deeper than necessary.** Start broad, identify the bottleneck, then zoom in.

```
Level 1 — Which job is slow?       (generic, always run first)
Level 2 — Which functions are hot? (generic, run on the slow module)
Level 3 — Why is that function slow? (custom per module)
```

---

## Level 1 — Workflow timing

**Goal:** Identify which job in a workflow consumes the most wall time.

**How it works:** Monkey-patches `AbstractOrchestrator._execute_job` to wrap each sub-step with a `perf_counter` timer. No modification to the source code required.

Each job is broken down into:

| Column | What it measures |
|--------|-----------------|
| `build` | Python model construction — variables, constraints, objective |
| `solve` | `SolverInterface.solve()` — solver call (LP/MIP, external C++) |
| `run` | `job.run()` — total of build + solve |
| `apply` | `CISHandler.apply()` — writing results back to the CIS |
| `export` | `cis.to_directory()` — optional disk export |

**Usage:**

```bash
atlas profiling --level workflow --parameters workflow.yaml
```

With a custom output path (default: `profiling_workflow`):

```bash
atlas profiling --level workflow --parameters workflow.yaml --output results/my_run
# Writes: results/my_run.json  and  results/my_run.csv
```

**Example output:**

```
──────────────────────────────────────────────────────────────
  Atlas Workflow — Level 1 Profile   wall=332.79s
──────────────────────────────────────────────────────────────
  Workflow.from_file                       0.04s    0%
  CurrentInputState.from_directory         4.33s    1%

  Job                     build   solve     run   apply  export   total  %
  ──────────────────────────────────────────────────────────────────────────────────
  DayAheadOrders         72.23s   3.46s  75.69s   0.12s   0.00s  75.81s  23%  ████
  MarketClearing         22.73s   0.11s  22.83s   0.11s   0.00s  22.94s   7%  █
  PortfolioOptimisation  27.22s  199.08s 226.30s   0.10s   0.00s 226.40s  68%  █████████████
  ──────────────────────────────────────────────────────────────────────────────────
  TOTAL                  122.18s 202.65s 324.83s   0.32s   0.00s 325.15s  98%

  Bottlenecks (> 5%):
    → PortfolioOptimisation · solve           199.08s  (60%)
    → DayAheadOrders · build                  72.23s  (22%)
    → PortfolioOptimisation · build           27.22s   (8%)
    → MarketClearing · build                  22.73s   (7%)

  build=yellow  solve=green  run=build+solve (dim)
──────────────────────────────────────────────────────────────
```

Two files are saved alongside the console output:

| File | Content |
|------|---------|
| `profiling_workflow.json` | Structured data — wall time, global steps, per-job breakdown |
| `profiling_workflow.csv` | Two-section CSV — global steps, then job steps with `pct_wall` |

**Decision rule:**

| Dominant column | Diagnosis | Next step |
|----------------|-----------|-----------|
| `build` | Python model construction is the bottleneck | Run Level 2 on that module |
| `solve` | Solver time dominates — LP/MIP formulation issue | Review formulation, not Python code |
| `apply` | I/O or serialization issue | Investigate the CIS layer |
| `export` | Disk write bottleneck | Check output volume |

---

## Level 2 — Function-level profiling

**Goal:** Identify which functions inside the slow module consume the most CPU time.

**Tools:** `pyinstrument` (visual call tree) + `cProfile` (statistical breakdown)

**Usage:**

```bash
atlas profiling --level module \
  --parameters path/to/parameters.yaml \
  --module DayAheadOrders \
  --dataset path/to/dataset/
```

With a custom output path (default: `profile_<ModuleName>`):

```bash
atlas profiling --level module \
  --parameters path/to/parameters.yaml \
  --module DayAheadOrders \
  --dataset path/to/dataset/ \
  --output results/dao_profile
# Writes: results/dao_profile.html  and  results/dao_profile_stats.txt
```

Two files are produced:

| File | Tool | Use |
|------|------|-----|
| `profile_<Module>.html` | pyinstrument | Interactive call tree — open in a browser |
| `profile_<Module>_stats.txt` | cProfile | Top 100 functions sorted by cumulative time |

**What to look for in the cProfile stats:**

| Metric | Meaning |
|--------|---------|
| `tottime` (self time) | Time in this function only — the real hotspot |
| `cumtime` (cumulative) | Time including all callees — useful for locating the call path |
| `ncalls` | Call count — high count on a slow function is the typical pattern |

**Decision rule:**

- A small set of functions with high `tottime` → those are the targets for Level 3
- Unexpectedly high `ncalls` (e.g. `get_value`, `get_forecast`) → redundant computation, likely cacheable

---

## Level 3 — Module-specific instrumentation

**Goal:** Understand *why* a specific function is slow and validate a fix.

**How it works:** Manual instrumentation with `perf_counter` timers inserted directly into the module's hot path. Unlike Levels 1 and 2, this is written specifically for the module being investigated.

!!! note
    Optimising the build phase has a hard ceiling at the solve time. If the solver consumes the full timeout, no build optimisation will improve wall time — the MIP gap or the timeout itself must be addressed instead.

---

## Decision flowchart

```
Run Level 1  (atlas profiling --level workflow ...)
     │
     ├── build dominates  →  Run Level 2 on that module
     │                       (atlas profiling --level module ...)
     │                              │
     │                              └── high tottime/ncalls  →  Level 3
     │
     ├── solve dominates  →  LP/MIP formulation issue — not a Python-level fix
     │
     ├── apply dominates  →  Investigate the CIS layer
     │
     └── export dominates →  Check output volume / disk throughput
```
