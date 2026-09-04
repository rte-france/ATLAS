# Action Plan Job

An `ActionPlanJob` is a single job produced for one iteration of a [`TaskModule`](task.md), executing a module against the current dataset and producing an output dataset — the same role [`WorkflowJob`](../workflow/workflow_step.md) plays for a `Workflow` step.

Jobs for a `TaskWorkflow` are not `ActionPlanJob` instances: each iteration builds a full nested [`Workflow`](../workflow/workflow.md), so its own `WorkflowJob`s are yielded directly into the action plan's job stream.

::: atlas.orchestrator.actionplan.job.ActionPlanJob
    options:
        show_if_no_docstring: false
