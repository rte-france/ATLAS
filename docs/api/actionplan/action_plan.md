# Action Plan

An `ActionPlan` is a structure for managing the sequential execution of multiple modules and workflows through a scheduled set of [`Tasks`](task.md). Like [`Workflow`](../workflow/workflow.md), it builds on the same orchestrator base: it executes a stream of jobs against a `CurrentInputState`, applying each job's [ChangeSets](../orchestrator/change_set.md) through the [`CISHandler`](../orchestrator/cis_handler.md), with the same support for rollback and job snapshots.

The key difference from `Workflow` is *scheduling*. A `Workflow` runs a fixed, ordered list of steps once. An `ActionPlan` instead runs each task repeatedly over its own time window (`from_` → `until`) at its own frequency, interleaving all tasks by execution date and priority to produce a single ordered stream of jobs.

Each task runs one of two things:

| Class | Runs |
|---|---|
| `TaskModule` | A single module, on each iteration |
| `TaskWorkflow` | A nested [`Workflow`](../workflow/workflow.md), on each iteration |

Two tasks in the same action plan cannot be **concurrent**: if they share the same priority and would, at some point, need to be executed for the same iteration, building the action plan raises a `ValueError`. See [`Task`](task.md) for details.

::: atlas.orchestrator.actionplan.action_plan.ActionPlan
    options:
        show_if_no_docstring: false
