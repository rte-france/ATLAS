# Task

A **Task** describes *when* and *how often* a module or a workflow runs inside an [`ActionPlan`](action_plan.md):
its time window (`from` / `until`), its execution `frequency`, optional offsets applied to the start and end dates
of each run, and a scheduling `priority` used to order tasks that fall on the same execution date.

For iteration *n* (1-based):

| | Value |
|---|---|
| `execution_date` | `from + (n - 1) × frequency` |
| `start_date` | `execution_date + offset_start_date` |
| `end_date` | `execution_date + offset_end_date` |
| iteration count | `⌊(until − from) / frequency⌋ + 1` |

If `until − from` is not a multiple of `frequency`, the last execution date falls short of `until` and a
`DataQualityWarning` is emitted. An `until` before `from` is a validation error.

There are two concrete task types:

| Class | Runs |
|---|---|
| [`TaskModule`](task.md) | A single module on each iteration |
| [`TaskWorkflow`](task.md) | A [`Workflow`](../workflow/workflow.md) on each iteration |

## Concurrency

Adding a concurrent task to an `ActionPlan` raises a `ValueError` — see `Task.are_concurrent` below for what
"concurrent" means. This is checked both when an `ActionPlanParameters` is built and whenever
[`ActionPlan.add_task`](action_plan.md) is called directly. Tasks with different priorities are never concurrent.

## Field Names

`from` is a Python keyword, so the field is `from_` in code. In YAML both `from` and `from_` are accepted.

## Task (base)

::: atlas.orchestrator.actionplan.parameters.Task
    options:
        show_if_no_docstring: true

## TaskModule

::: atlas.orchestrator.actionplan.parameters.TaskModule
    options:
        show_if_no_docstring: true

## TaskWorkflow

::: atlas.orchestrator.actionplan.parameters.TaskWorkflow
    options:
        show_if_no_docstring: true
