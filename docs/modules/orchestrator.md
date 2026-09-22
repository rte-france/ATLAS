# Orchestrator

An **orchestrator** is what runs modules against a dataset. Atlas provides two:

| Orchestrator | Runs | Page |
|---|---|---|
| `Workflow` | A fixed, ordered list of **steps**, once | [Run a Workflow](workflow.md) |
| `ActionPlan` | A set of **tasks**, each repeated on its own schedule | [Run an Action Plan](action-plan.md) |

Both derive from `AbstractOrchestrator`, which owns everything described on this page: loading the dataset,
running jobs in order, applying each job's changes to the shared state, rollback, snapshots, and the final export.
The only thing the two subclasses provide is *which jobs to run, in what order*.

---

## Execution Model

### Jobs

A **job** is one module execution: a name, a module class, and the fully resolved parameters for that run. Steps
and task iterations both end up as jobs — `WorkflowJob` and `ActionPlanJob` are thin subclasses of `AbstractJob`
that differ only in how they print themselves.

Every orchestrator exposes:

- `jobs` — an **iterator** producing the jobs to run, in execution order
- `jobs_count` — how many jobs are expected (see the [caveat for action plans](action-plan.md#scheduling))

!!! warning "`jobs` is a generator"
    Each access to `orchestrator.jobs` builds a **fresh set of unexecuted jobs**. It is not a record of the last
    run: iterating it after `execute()` yields new objects whose `get_output_dataset()` is `None`. Use the value
    returned by `execute()`, or exported output directories, to read results.

### The Current Input State

The [`CurrentInputState`](../api/orchestrator/current_input_state.md) (CIS) is the single mutable state threaded
through a run. It wraps an [`AtlasDataset`](../api/io/atlas_dataset.md) and adds snapshots, rollback, diffing and
transactions.

Modules never write to it directly. Each job receives a **deep copy** of the current data, runs, and returns an
output object carrying a list of [ChangeSets](../api/orchestrator/change_set.md) — `AddObject`, `UpdateObject`,
`DeleteObject`. The [`CISHandler`](../api/orchestrator/cis_handler.md) is the only component that applies them.

### The Run Loop

`execute()` performs the following, and returns the final CIS:

1. Load the dataset from `dataset_path` into a new CIS.
2. If `create_job_snapshots`, snapshot it as `<Workflow|ActionPlan>_input`.
3. For each job, in order:
    1. If `create_job_snapshots`, snapshot the state as `input_<job name>`.
    2. Hand the job a deep copy of the current data and run its module.
    3. Order the resulting ChangeSets by model instantiation order, warn about several ChangeSets targeting the
       same object, then apply them to the CIS through the `CISHandler`.
    4. If the job's module parameters set `output.export_output_dataset`, write the CIS to
       `<that job's output.output_dir>/output_dataset`.
4. Record the last job's module output as the orchestrator's `final_dataset`.
5. If `export_output`, write the CIS to `<output_dir>/workflow_output` or `<output_dir>/actionplan_output`.

Each job therefore sees the cumulative effect of every job before it — this is what makes a workflow a chain, and
what lets the tasks of an action plan interact across a rolling horizon.

### Failure Handling

Any exception raised by a job is wrapped in a `WorkflowJobError` carrying the job name, the CIS and, where
relevant, the input dataset. Whatever else happens, the orchestrator stops: jobs that already succeeded stay
applied, and no later job runs.

---

## Orchestrator Parameters

`Workflow` and `ActionPlan` parameters both inherit these fields; each adds its own list (`steps` / `tasks`).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | str \| null | `null` | Name of the orchestrator, used in logs |
| `dataset_path` | path | — | **Required.** Initial input dataset directory |
| `output_dir` | path | `.` | Root for per-job results and the final export |
| `path_from_orchestrator` | bool | `false` | Resolve relative paths from `orchestrator_path` |
| `orchestrator_path` | path | current working directory | Absolute root path used when the flag above is `true` |
| `rollback_on_job_failure` | bool | `true` | Roll back touched containers when a job fails |
| `create_job_snapshots` | bool | `false` | Snapshot the state before the run and before each job |
| `export_output` | bool | `true` | Export the final state at the end of the run |
| `context` | [ContextParameters](context.md) | `{}` | Defaults and forced values applied to every job's parameters |

`path_from_orchestrator` and `orchestrator_path` each accept two aliases, so the same field can be written in the
vocabulary of whichever orchestrator you are configuring:

| Generic | Workflow alias | Action plan alias |
|---|---|---|
| `path_from_orchestrator` | `path_from_workflow` | `path_from_action_plan` |
| `orchestrator_path` | `workflow_path` | `action_plan_path` |

### Path Resolution

Every path in an orchestrator configuration goes through the same rule:

- an **absolute** path is used as-is;
- a **relative** path is resolved from `orchestrator_path` when `path_from_orchestrator` is `true`, and from the
  process's current working directory otherwise.

`from_file` sets `orchestrator_path` to the directory containing the configuration file, so
`path_from_orchestrator: true` makes a configuration folder self-contained and movable. With the flag on,
`orchestrator_path` must be an existing absolute path or validation fails.

---

## Advanced Options

### Rollback on Failure

With `rollback_on_job_failure: true` (the default), applying a job's ChangeSets runs inside a transaction: only
the containers that job touches are backed up, and they are restored if any ChangeSet fails. This keeps the state
consistent without the cost of copying the whole dataset.

```yaml
rollback_on_job_failure: true  # safe default — always restore on failure
```

Set it to `false` only if you want to inspect the state at the exact point of failure, partial changes included.

Rollback covers the **failing job only**. It does not undo jobs that already completed.

### Snapshots

With `create_job_snapshots: true`, the CIS keeps a labelled deep copy of the data before the run and before every
job:

```yaml
create_job_snapshots: true
```

| Orchestrator | Initial snapshot | Per-job snapshot |
|---|---|---|
| `Workflow` | `Workflow_input` | `input_'<step name>'` |
| `ActionPlan` | `ActionPlan_input` | `input_task '<task name>' iteration <n>` |

When a job fails, the available labels are written to the log. Snapshots are held in memory, so they cost roughly
one dataset copy each — useful for debugging, expensive on long action plans. `clear_history()` frees them.

From Python, snapshots support inspection and re-runs:

```python
cis.list_snapshots()
cis.get_snapshot("Workflow_input")          # read without changing the state
cis.restore_snapshot("Workflow_input")      # roll the state back
cis.diff(label="Workflow_input")            # what changed since
```

`diff` reports added, removed and modified object names per model type.

### Exporting the Final State

With `export_output: true` (the default), the final CIS is written at the end of the run to
`<output_dir>/workflow_output` or `<output_dir>/actionplan_output`. Timeseries and matrices are written as
parquet.

Per-job exports are controlled by the **module** parameters instead, through
[`output.export_output_dataset`](common-parameters.md#output-output-configuration-optional). The orchestrator
rewrites each job's `output.output_dir` before the run:

| Orchestrator | Per-job `output_dir` |
|---|---|
| `Workflow` step | `<output_dir>/<step name>` |
| `ActionPlan` `TaskModule` iteration | `<output_dir>/<task name>/<execution date>` |
| `ActionPlan` `TaskWorkflow` step | `<the inner workflow's output_dir>/<prefixed step name>` — see the [caveat](action-plan.md#directory-layout) |

---

## Common API

Both orchestrators expose the same surface:

```python
orchestrator = Workflow.from_file("workflow.yaml")   # or ActionPlan.from_file(...)
orchestrator.use_context(context)                    # merge in a context (see the caveat below)
cis = orchestrator.execute()                         # run; returns the final CurrentInputState
output = orchestrator.get_output_dataset()           # last job's module output, or None
```

| Member | Description |
|---|---|
| `from_file(path, context=None)` | Build from YAML/JSON, optionally merging a [context](context.md) that takes priority over the file's |
| `use_context(context)` | Merge a context into the parameters, overwriting overlapping keys |
| `execute()` | Run every job in order; returns the final `CurrentInputState` |
| `get_output_dataset()` | The **last executed job's** module output (with its ChangeSets), or `None` |
| `jobs` / `jobs_count` | The job iterator and the expected job count |

!!! warning "`use_context` after construction is usually too late"
    A `Workflow` resolves each step's parameters against the context in its **constructor**, and an `ActionPlan`
    does the same for each task. Calling `use_context()` afterwards updates `parameters.context` but does not
    re-resolve jobs already built. Pass the context to `from_file`, or put it in the configuration file.

---

## See Also

- [Context](context.md): how `default` and `forced` values reach module parameters
- [Run a Workflow](workflow.md) · [Run an Action Plan](action-plan.md)
- [CurrentInputState](../api/orchestrator/current_input_state.md) · [ChangeSets](../api/orchestrator/change_set.md) · [CISHandler](../api/orchestrator/cis_handler.md)
- [Common Parameters](common-parameters.md): the module-level parameters an orchestrator fills in
