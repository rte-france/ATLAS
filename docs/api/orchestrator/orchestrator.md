# AbstractOrchestrator

`AbstractOrchestrator` is the base class of [`Workflow`](../workflow/workflow.md) and
[`ActionPlan`](../actionplan/action_plan.md). It owns the whole run: loading the dataset into a
[`CurrentInputState`](current_input_state.md), executing [`jobs`](orchestrator_job.md) in order, applying their
[ChangeSets](change_set.md) through the [`CISHandler`](cis_handler.md), rollback, snapshots and the final export.

Subclasses only supply the jobs: `jobs`, `jobs_count` and `get_param_class`.

See [Orchestrator](../../modules/orchestrator.md) for the conceptual guide.

::: atlas.abstract_class.orchestrator.AbstractOrchestrator
    options:
        show_if_no_docstring: true