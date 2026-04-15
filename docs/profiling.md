# Profiling Methodology — ATLAS

## Core principle

**Never go deeper than necessary.** Start broad, identify the bottleneck, then zoom on in

```
Level 1 — Which module is slow? (generic, always run first)
Level 2 — Which functions are called? (generic, run on the slow module)
Level 3 — Why is that function slow? (custom per module)
```

---

## Level 1 — Workflow timing

**Goal:** Identify which module consumes the most wall time.

**Script:** `profiling_level1.py`

**How it works:** Monkey-patches `AbstractOrchestrator._execute_job` to wrap each sub-step with a `perf_counter` timer. No modification to the source code required.

Each job is broken down into:

| Column | What it measures |
|--------|-----------------|
| `filter` | `cis.filter_dataset()` — dataset filtering before the module runs |
| `build` | Python model construction — variables, constraints, objective |
| `solve` | `SolverInterface.solve()` — solver call (LP/MIP, external C++) |
| `run` | `job.run()` — total of build + solve |
| `apply` | `CISHandler.apply()` — writing results back to the CIS |
| `export` | `cis.to_directory()` — optional disk export |

**Usage:**

```bash
python profiling_level1.py --parameters workflow.yaml
```

**Example output:**

```
──────────────────────────────────────────────────────────────
  Atlas Workflow — Level 1 Profile   wall=104.41s
──────────────────────────────────────────────────────────────
  Workflow.from_file                       0.01s    0%
  CurrentInputState.from_directory         0.66s    1%
  Job                    filter   build   solve     run   apply  export   total  %
  ──────────────────────────────────────────────────────────────────────────────────
  DayAheadOrders          0.01s  63.48s   3.16s  66.64s   0.07s   0.00s  66.72s  64%  ████████████
  MarketClearing          0.67s  19.84s   0.15s  20.00s   0.10s   0.00s  20.77s  20%  ███
  PortfolioOptimisation   0.02s  14.55s   0.13s  14.67s   0.08s   0.00s  14.77s  14%  ██
  ──────────────────────────────────────────────────────────────────────────────────
  TOTAL                   0.70s  97.87s   3.44s 101.31s   0.25s   0.00s 102.26s  98%
  Bottlenecks (> 5%):
    → DayAheadOrders · build                    63.48s  (61%)
    → MarketClearing · build                    19.84s  (19%)
    → PortfolioOptimisation · build             14.55s  (14%)
  build=yellow  solve=green  run=build+solve (dim)
──────────────────────────────────────────────────────────────
```

**Decision rule:**

- `build` dominates → go to Level 2 on that module
- `solve` dominates → LP or MIP is independent of Python code — LP/MIP formulation may need to change
- `filter` or `apply` dominates → I/O or serialization issue, investigate the CIS layer
- `export` dominates → disk write bottleneck, check output volume

---

## Level 2 — Function-level profiling

**Goal:** Identify which functions inside the slow module consume the most CPU time.

**Tool:** Python standard library `cProfile`

**How it works:** Wraps the module's `run()` call with a profiler. Reports cumulative time (`cumtime`) and self time (`tottime`) per function. No modification to the source code required.

**Usage:**

```bash
python profiling_level2.py --parameters workflow.yaml --module DayAheadOrders
```

**What to look for:**

| Metric | Meaning |
|--------|---------|
| `tottime` (self time) | Time spent in this function only — identifies the real hotspot |
| `cumtime` (cumulative) | Time including all callees — useful for locating the call path |
| `ncalls` | Number of calls — high call count on a slow function is the typical pattern |

**Decision rule:**

- A small set of functions with high `tottime` → those are the targets for Level 3
- Unexpectedly high `ncalls` on a function (e.g. `get_value`, `get_forecast`) → redundant computation, likely cacheable

---

## Level 3 — Module-specific instrumentation

**Goal:** Understand *why* a specific function is slow and validate a fix.

**How it works:** Manual instrumentation with `perf_counter` timers, inserted directly into the module's hot path. Unlike Levels 1 and 2, this is written specifically for the module being investigated.

TODO

**Important limits at Level 3:**

- Optimising the build phase (model construction) has a hard ceiling at the solve time
- If the solver consumes the full timeout, no build optimisation will improve wall time — the MIP gap or the timeout itself must be addressed instead

---

## Decision flowchart

```
Run Level 1
     │
     ▼
run >> 
  ├── build dominates → Run Level 2 on that module
  │
  ├── solver dominates : LP/MIP formulation issue, not a Python-level fix
  │
  └── filter/apply dominates : Check on Atlas API function
```

---

## Files

| File | Level | Scope |
|------|-------|-------|
| `profiling_level1.py` | 1 | Generic — any Atlas workflow |
| `profiling_level2.py` | 2 | Generic — wraps any module's `run()` with cProfile |