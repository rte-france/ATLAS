# Run an Action Plan

An action plan runs a set of **tasks** on a recurring schedule — each task runs a module or a
[workflow](workflow.md) repeatedly over its own time window, at its own frequency. Unlike a
[workflow](workflow.md), which runs a fixed list of steps once, an action plan is built for rolling-horizon
simulations: run `PortfolioOptimisation` every day for a month, or run a full day-ahead `Workflow` every week.

All tasks share the same [Current Input State](orchestrator.md#the-current-input-state): the scheduler merges every
task's iterations into a single ordered stream of jobs, and each job sees the state left by the job before it.

An action plan is the second of the two [orchestrators](orchestrator.md) provided by Atlas, and shares its
execution model, rollback, snapshot and export behaviour with `Workflow`.

---

## Define an Action Plan

An action plan is defined in a YAML (or JSON) file:

```yaml
name: monthly-portfolio
dataset_path: ./data/input/
output_dir: ./results/
tasks:
  - name: daily-portfolio
    module: PortfolioOptimisation
    parameters: ./parameters/portfolio_optimisation.yml
    from: '2028-01-01 00:00:00'
    until: '2028-01-31 00:00:00'
    frequency: 1d
    offset_start_date: 0m
    offset_end_date: 1d
```

As with a workflow, two different types of parameters are present in this file:

- **Top-level parameters** either define global information (such as the action plan name), or are applied to
  *every* task.
- **Task parameters** define what a given task runs, and when.

### Top-level Parameters

Every action plan inherits the [common orchestrator parameters](orchestrator.md#orchestrator-parameters):

| Parameter | Required | Default | Description |
|---|---|---|---|
| `name` | No | `null` | Name of the action plan |
| `dataset_path` | Yes | — | Path to the initial input dataset |
| `output_dir` | No | `.` | Root directory for per-task, per-iteration results and for the final export |
| `path_from_action_plan` | No | `false` | Resolve relative paths from `action_plan_path` |
| `action_plan_path` | No | directory of the action plan file | Absolute root path used when `path_from_action_plan` is `true` |
| `rollback_on_job_failure` | No | `true` | Roll back the state to before the failed job |
| `create_job_snapshots` | No | `false` | Save a state snapshot before each job |
| `export_output` | No | `true` | Export the final state to `<output_dir>/actionplan_output` |
| `context` | No | `{}` | [Context](context.md) of default and forced values applied to every task |
| `hooks` | No | `[]` | Reserved for future callback support — `Hook` is a placeholder and is not called |
| `tasks` | Yes | — | List of tasks |

!!! note "Parameter aliases"
    `path_from_action_plan` and `action_plan_path` are aliases of the generic `path_from_orchestrator` and
    `orchestrator_path` fields shared with [workflows](workflow.md). Either spelling is accepted.

### Task Parameters

Every task, whichever type it runs, shares the same scheduling fields:

| Parameter | Required | Default | Description |
|---|---|---|---|
| `name` | No | module / workflow name | Custom name for the task |
| `from` | Yes | — | First execution date for this task |
| `until` | Yes | — | Last execution date for this task |
| `frequency` | No | `1m` | Interval between two consecutive executions |
| `offset_start_date` | No | `0m` | Offset from the execution date used as the run's `start_date` |
| `offset_end_date` | No | `0m` | Offset from the execution date used as the run's `end_date` |
| `priority` | No | `0` | Tie-breaker when two tasks execute on the same date — lower runs first |

`frequency`, `offset_start_date`, and `offset_end_date` accept the same duration syntax as elsewhere in Atlas
(`15m`, `1h`, `1d`, `1d30m`, or ISO 8601 such as `PT1H`). Negative durations are rejected.

For iteration *n* (1-based), the dates handed to the run are:

| | Value |
|---|---|
| `execution_date` | `from + (n - 1) × frequency` |
| `start_date` | `execution_date + offset_start_date` |
| `end_date` | `execution_date + offset_end_date` |

!!! note "`until` is a bound, not necessarily an execution date"
    The number of iterations is `⌊(until − from) / frequency⌋ + 1`. If `until − from` is not an exact multiple of
    `frequency`, the last execution date falls before `until` and Atlas emits a `DataQualityWarning` telling you
    what the real last execution date is. An `until` earlier than `from` is a validation error.

On top of these, exactly one of two task types must be chosen:

| Field | Task type | Description |
|---|---|---|
| `module` + `parameters` | `TaskModule` | Runs a single module (`DayAheadOrders`, `IntradayOrders`, `IntradayPriceForecast`, `MarketClearing`, `PortfolioOptimisation`) on each iteration. `parameters` is a path to a parameters file or an inline mapping. |
| `workflow` | `TaskWorkflow` | Runs a [`Workflow`](workflow.md) on each iteration. `workflow` is a path to a workflow YAML file or an inline mapping with the same shape as a workflow config. |

!!! note "Concurrent tasks"
    Two tasks that share the same `priority` and would, at some point, be scheduled on the same execution date
    cannot both belong to the same action plan — the action plan raises a `ValueError`, both when the parameters
    are validated and when `add_task` is called directly. Give tasks that may land on the same date different
    priorities. Tasks with different priorities are never considered concurrent.

!!! note "Placeholder dates in module parameters"
    A `TaskModule`'s own parameters file still needs a `temporal` block with *some*
    `start_date`/`end_date`/`execution_date` to pass initial validation — Atlas overwrites all three with the
    task's real per-iteration dates before each run. Only `timestep` is kept from what you provide. The same
    applies to the module parameters of a `TaskWorkflow`'s steps.

#### Inline Parameters

As with workflow steps, a task's module parameters — or an entire workflow — can be written directly in the
action plan YAML instead of pointing to a separate file:

```yaml
name: monthly-portfolio
dataset_path: ./data/input/
output_dir: ./results/
tasks:
  - module: PortfolioOptimisation
    parameters:
      temporal:
        start_date: '2000-01-01 00:00:00'
        end_date: '2000-01-02 00:00:00'
        execution_date: '2000-01-01 00:00:00'
    from: '2028-01-01 00:00:00'
    until: '2028-01-31 00:00:00'
    frequency: 1d
```

#### Default Task Names

If `name` is omitted, the task is named after what it runs: the module name for a `TaskModule`; for a
`TaskWorkflow`, the workflow's `name`, or the file stem when the workflow is given as a path. Duplicate task names
are deduplicated with `_1`, `_2`, … exactly as [workflow step names](workflow.md#step-parameters) are. Task names
become output directory names, so explicit names are worth setting.

---

## Run

### Python

```python
from atlas.orchestrator.actionplan.action_plan import ActionPlan

action_plan = ActionPlan.from_file("action_plan.yaml")
cis = action_plan.execute()
```

Unlike `Workflow`, `ActionPlan` is not re-exported at the top level of the package — import it from
`atlas.orchestrator.actionplan.action_plan`.

`from_file` also accepts a [context](context.md) that takes priority over the one declared in the file:

```python
from atlas.io_utils.parameters import ContextParameters

action_plan = ActionPlan.from_file(
    "action_plan.yaml",
    ContextParameters(forced={"solver": {"solver_name": "SCIP"}}),
)
```

!!! warning "No CLI command yet"
    There is currently **no** `atlas action-plan` command. Action plans are run from Python only. The
    [CLI](../cli.md) covers modules and workflows.

### Programmatic

You can also build an action plan directly in Python, without a YAML file:

```python
from atlas import Workflow, WorkflowParameters
from atlas.orchestrator.actionplan.action_plan import ActionPlan
from atlas.orchestrator.actionplan.parameters import ActionPlanParameters, TaskModule, TaskWorkflow
from atlas.orchestrator.workflow.parameters import Step

workflow = Workflow(WorkflowParameters(
    dataset_path="./data/input/",
    steps=[Step(module="DayAheadOrders", parameters="./parameters/day_ahead_orders.yml")],
))

parameters = ActionPlanParameters(
    name="monthly-portfolio",
    dataset_path="./data/input/",
    output_dir="./results/",
    tasks=[
        TaskModule(
            name="daily-portfolio",
            module="PortfolioOptimisation",
            parameters="./parameters/portfolio_optimisation.yml",
            from_="2028-01-01 00:00:00",
            until="2028-01-31 00:00:00",
            frequency="1d",
        ),
        TaskWorkflow(
            name="weekly-day-ahead",
            workflow=workflow,
            priority=1,
            from_="2028-01-01 00:00:00",
            until="2028-01-31 00:00:00",
            frequency="7d",
        ),
    ],
)

action_plan = ActionPlan(parameters=parameters)
cis = action_plan.execute()
```

Note the trailing underscore: `from` is a Python keyword, so the field is `from_` in code (the YAML key remains
`from`, and `from_` is accepted there too).

Tasks can also be added after construction with `add_task`, which raises a `ValueError` if the new task is
concurrent with one already present:

```python
action_plan.add_task(TaskModule(...))
```

---

## Scheduling

The scheduler interleaves every task's iterations into a single ordered stream of jobs, sorted first by execution
date, then by `priority` for iterations landing on the same date:

```yaml
tasks:
  - name: fast-check
    priority: 0    # runs first on shared dates
    frequency: 1d
    ...
  - name: full-run
    priority: 1    # runs second on shared dates
    frequency: 7d
    ...
```

A `TaskModule` iteration produces exactly one job. A `TaskWorkflow` iteration produces **one job per step of the
workflow**, all of them emitted consecutively before the next task's iteration; the workflow is rebuilt for each
iteration with that iteration's dates.

!!! note "`jobs_count` counts iterations, not jobs"
    `ActionPlan.jobs_count` — and the `n/total` progress counter in the logs — sums the number of *iterations*
    across tasks. A `TaskWorkflow` with several steps therefore yields more jobs than `jobs_count` announces, and
    the progress counter can run past the total. `len(list(action_plan.jobs))` gives the real number of jobs.

---

## Accessing Results

`execute()` returns the final [`CurrentInputState`](../api/orchestrator/current_input_state.md) — the input
dataset with the changes of every job applied, in schedule order:

```python
cis = action_plan.execute()
dataset = cis.get_data()

for order in dataset.order.all():
    print(f"{order.name}: {order.accepted_power} MW")
```

`get_output_dataset()` returns the module output object produced by the **last executed job**, carrying that
module's own results and its [ChangeSets](../api/orchestrator/change_set.md), or `None` if the action plan has not
run to the end. As with workflows, `action_plan.jobs` is a generator of fresh, unexecuted jobs — iterating it after
`execute()` does not give you the results of the run. To keep per-iteration results, rely on the exported output
directories below.

---

## Directory Layout

A typical action plan project:

```
my-action-plan/
├── action_plan.yaml
├── data/
│   └── input/                              # Initial dataset (dataset_path)
├── parameters/
│   └── portfolio_optimisation.yml
└── results/                                # output_dir
    ├── daily-portfolio/                    # one directory per TaskModule
    │   ├── 2028-01-01T00:00:00+00:00/
    │   ├── 2028-01-02T00:00:00+00:00/
    │   └── ...
    └── actionplan_output/                  # final state, when export_output is true
```

For a `TaskModule`, each iteration's module parameters get their `output.output_dir` set to
`<output_dir>/<task name>/<execution date>/`. Files are only written there if the module parameters set
`output.export_output_dataset: true` (or `export_result`).

!!! warning "A `TaskWorkflow` does not write under the action plan's `output_dir`"
    The action plan forces a per-iteration output directory into the workflow's [context](context.md), but the
    workflow overwrites each step's `output.output_dir` with `<the workflow's own output_dir>/<step name>` when it
    builds its steps. Step outputs of a `TaskWorkflow` therefore land under the **workflow's** `output_dir`, not
    the action plan's.

    Iterations do not collide, because the step name carries the task and iteration:

    ```
    <workflow output_dir>/
    ├── task 'weekly-day-ahead' iteration 1 DayAheadOrders/
    ├── task 'weekly-day-ahead' iteration 1 MarketClearing/
    ├── task 'weekly-day-ahead' iteration 2 DayAheadOrders/
    └── ...
    ```

    Set the inner workflow's `output_dir` explicitly if you want those results in a predictable place.

When `path_from_action_plan: true`, all relative paths in `action_plan.yaml` are resolved from
`action_plan_path` — which `ActionPlan.from_file` sets to the directory containing the action plan file — so you
can move the whole folder without breaking paths. Absolute paths are always used as-is.

---

## Advanced Options

Rollback, snapshots and the final export behave identically for workflows and action plans; they are documented
once in [Orchestrator](orchestrator.md#advanced-options). In short:

| Option | Default | Effect |
|---|---|---|
| `rollback_on_job_failure` | `true` | On failure, restore the containers touched by the failing job |
| `create_job_snapshots` | `false` | Snapshot the state before the action plan and before each job |
| `export_output` | `true` | Write the final state to `<output_dir>/actionplan_output` |

With `create_job_snapshots: true`, an action plan creates one snapshot named `ActionPlan_input` before the first
job, then one named `input_task '<task name>' iteration <n>` before each job. Snapshot labels are listed in the
logs when a job fails.

Because every job in the schedule reads and writes the same state, `rollback_on_job_failure` only undoes the
**failing job**. Jobs that already succeeded stay applied; the action plan stops at the failure with a
`WorkflowJobError` carrying the job name and the state.

---

## See Also

- [Orchestrator](orchestrator.md): the execution model shared by workflows and action plans
- [Context](context.md): defaults and forced values applied to every task
- [Run a Workflow](workflow.md): running a fixed, one-shot sequence of modules
- [Common Parameters](common-parameters.md): parameters shared by all modules
- [Action Plan API Reference](../api/actionplan/action_plan.md): full API documentation
- [Task API Reference](../api/actionplan/task.md): `Task`, `TaskModule`, and `TaskWorkflow` details
