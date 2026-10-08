# Context

A **context** is a set of parameter values an [orchestrator](orchestrator.md) applies to *every* module it runs.
It exists so that a value shared by all steps or tasks — an execution date, a solver, an output flag — is written
once in the orchestrator configuration instead of being repeated in each module parameters file.

A context has exactly two blocks:

| Block | Applies when | Precedence |
|---|---|---|
| `default` | The module parameters leave the value unset | Lowest — the module's own value wins |
| `forced` | Always | Highest — overrides the module's own value |

```yaml
name: day-ahead
dataset_path: ./data/input/
context:
  default:
    temporal:
      execution_date: '2028-09-26 12:00:00'
  forced:
    solver:
      solver_name: 'SCIP'
steps:
  - module: MarketClearing
    parameters: ./parameters/market_clearing.yml
```

Here every step gets `solver_name: SCIP` whatever its own file says, and gets that `execution_date` only if its
own file does not provide one.

The same `context` block works identically in a [workflow](workflow.md) and an [action plan](action-plan.md).

!!! note "Merging is **deep**"
    a context touching `temporal.execution_date` leaves `temporal.start_date` alone.
    Nested mappings are merged key by key rather than replaced wholesale.
---

## Precedence

For any given key, the winner is:

```
forced  >  module parameters  >  default
```

A worked example — with these module parameters:

```yaml
temporal:
  start_date: '2028-01-05 00:00:00'
  timestep: '15m'
solver:
  solver_name: 'SCIP'
```

and this context:

```yaml
context:
  default:
    temporal:
      start_date: '1999-01-01 00:00:00'
      end_date: '2028-01-06 00:00:00'
      execution_date: '2028-01-04 12:00:00'
    solver:
      solver_name: 'HIGHS'
  forced:
    solver:
      duality_gap: 0.05
```

the module ends up running with:

| Parameter | Value | Why |
|---|---|---|
| `temporal.start_date` | `2028-01-05 00:00:00` | The module set it — `default` does not apply |
| `temporal.end_date` | `2028-01-06 00:00:00` | The module left it unset — filled by `default` |
| `temporal.execution_date` | `2028-01-04 12:00:00` | The module left it unset — filled by `default` |
| `temporal.timestep` | `15m` | The module set it |
| `solver.solver_name` | `SCIP` | The module set it — `default` loses |
| `solver.duality_gap` | `0.05` | `forced` always wins |

---

## Context priority on multi-declaration

There are three sources where an orchestrator context can be defined, they are applied in this order — later ones overwrite earlier ones on **overlapping keys**:

1. The `context` block in the orchestrator's configuration file.
2. A `ContextParameters` passed to `from_file`.
3. A `ContextParameters` passed to `use_context()`.

```python
from atlas import Workflow
from atlas.io_utils.parameters import ContextParameters

workflow = Workflow.from_file(
    "workflow.yaml", # note: may contain a context
    ContextParameters(forced={"solver": {"solver_name": "SCIP"}}),
)
workflow.execute()

workflow.use_context(ContextParameters(forced={"solver": {"solver_name": "XPRESS"}}))
workflow.execute()
```

This is the usual way to override a committed configuration for one run — a different solver, a shifted execution
date — without editing the file or rebuilding a new orchestrator.

---

## Contexts in Action Plans

Action plans use the same `context` block, applied to every task's module or workflow parameters.

They also use the context **internally**. For a `TaskWorkflow`, the per-iteration dates are injected by writing
them into the inner workflow's `forced` context before the workflow is built:

```yaml
forced:
  temporal:
    execution_date: <iteration execution date>
    start_date: <execution date + offset_start_date>
    end_date: <execution date + offset_end_date>
```

Two consequences are worth knowing:

- A `forced.temporal` entry you write yourself in a `TaskWorkflow`'s workflow file is **overwritten** by the
  action plan's scheduling dates. `timestep` is untouched, so per-module time resolution still comes from the
  module parameters.
- The forced `output.output_dir` does not survive: the workflow rewrites each step's output directory when it
  builds its steps. See the [action plan directory layout](action-plan.md#directory-layout).

A `TaskModule` does not go through the context for this — its dates are written straight into the module
parameters for each iteration.

---

## See Also

- [Orchestrator](orchestrator.md): where the context sits in the execution model
- [Run a Workflow](workflow.md) · [Run an Action Plan](action-plan.md)
- [Common Parameters](common-parameters.md): the module parameters a context can set
