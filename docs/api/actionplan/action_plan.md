# Action Plan

An **ActionPlan** is a structure for managing the execution of multiple modules and workflows through a scheduled
set of [`Tasks`](task.md) ; derive from [`AbstractOrchestrator`](../orchestrator/orchestrator.md).

An ActionPlan executes a stream of jobs against a [`CurrentInputState`](../orchestrator/current_input_state.md), applying each job's
[ChangeSets](../orchestrator/change_set.md) through the [`CISHandler`](../orchestrator/cis_handler.md), with the
same support for rollback and job snapshots.

An ActionPlan runs each [`Task`](task.md) over its own time window (`from` → `until`) at its own `frequency`, merging all tasks into a single stream of jobs ordered by execution date, then by task priority.

Each task runs one of two things:

| Class | Runs |
|---|---|
| [`TaskModule`](task.md) | A single module |
| [`TaskWorkflow`](task.md) | A [`Workflow`](../workflow/workflow.md) |

!!! note "Concurrency"
    Two tasks in the same action plan cannot be **concurrent**: if they share the same priority and would, at some
    point, be executed on the same date, building the action plan raises a `ValueError`. See [`Task`](task.md).

::: atlas.orchestrator.actionplan.action_plan.ActionPlan
    options:
        show_if_no_docstring: false

## ActionPlanParameters

::: atlas.orchestrator.actionplan.parameters.ActionPlanParameters
    options:
        show_if_no_docstring: true
