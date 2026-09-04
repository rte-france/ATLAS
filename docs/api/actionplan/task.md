# Task

A `Task` describes *when* and *how often* a Module or a Workflow runs inside an [`ActionPlan`](action_plan.md):
its time window (`from` / `until`), its execution `frequency`, an optional offset applied to the start dates and end dates of each run, and a scheduling `priority` used to order tasks that fall on the same execution date.

There are two concrete task types:

| Class | Runs |
|---|---|
| `TaskModule` | A single module on each iteration |
| `TaskWorkflow` | A [`Workflow`](../workflow/workflow.md) on each iteration |

## Concurrency

Adding a concurrent task to an `ActionPlan` raises a `ValueError` — see [`Task.are_concurrent`](#task-base) below for what "concurrent" means. This is checked automatically both when an `ActionPlanParameters` is built and whenever [`ActionPlan.add_task`](action_plan.md) is called directly.

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