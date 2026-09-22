# Action Plan

An **ActionPlan** is a structure for managing the execution of multiple modules and workflows through a scheduled
set of [`Tasks`](task.md).

Like [`Workflow`](../workflow/workflow.md), it executes a stream of jobs against a
[`CurrentInputState`](../orchestrator/current_input_state.md), applying each job's
[ChangeSets](../orchestrator/change_set.md) through the [`CISHandler`](../orchestrator/cis_handler.md), with the
same support for rollback and job snapshots. Both derive from
[`AbstractOrchestrator`](../orchestrator/orchestrator.md).

The key difference from [`Workflow`](../workflow/workflow.md) is *scheduling*. A [`Workflow`](../workflow/workflow.md) runs a fixed, ordered list of steps once. An
**ActionPlan** runs each task repeatedly over its own time window (`from` → `until`) at its own `frequency`, merging
all tasks into a single stream of jobs ordered by execution date, then by task priority.

Each task runs one of two things:

| Class | Runs |
|---|---|
| [`TaskModule`](task.md) | A single module |
| [`TaskWorkflow`](task.md) | A [`Workflow`](../workflow/workflow.md) |

!!! note "Concurrency"
    Two tasks in the same action plan cannot be **concurrent**: if they share the same priority and would, at some
    point, be executed on the same date, building the action plan raises a `ValueError`. See [`Task`](task.md).

!!! note "`jobs_count` counts iterations"
    `jobs_count` sums the number of iterations across tasks, so a `TaskWorkflow` with several steps produces more
    jobs than it reports.

::: atlas.orchestrator.actionplan.action_plan.ActionPlan
    options:
        show_if_no_docstring: false

## ActionPlanParameters

::: atlas.orchestrator.actionplan.parameters.ActionPlanParameters
    options:
        show_if_no_docstring: true
