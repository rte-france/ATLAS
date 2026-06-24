# Run a Workflow

A workflow chains multiple modules sequentially — the output dataset of each step becomes the input of the next.

---

## Define a Workflow

A workflow is defined in a YAML file:

```yaml
name: day-ahead
dataset_path: ./data/input/
output_dataset_path: ./data/output/
output_dir: ./results/
steps:
  - module: DayAheadOrders
    parameters_path: ./parameters/day_ahead_orders.yml
  - module: MarketClearing
    parameters_path: ./parameters/market_clearing.yml
  - module: PortfolioOptimisation
    parameters_path: ./parameters/portfolio_optimisation.yml
```

The order in which steps are written in the YAML is important: it defines the actual chain of modules in the simulation. The `module` field has to correspond to an existing module name (cf. the overview of each individual module for its name in the [Modules section](index.md)). For the (optional) `name` field, however, the user can choose whatever is best for clarity purposes.

Additionnaly, two different types of parameters are present in this YAML file:

- Top-level parameters either define global information (such as the workflow name), or are applied to *every* step in the chain.
- Step parameters are applied to a given step.

Possible options for these two types are detailed in the following sections.

### Top-level Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| `name` | No | `null` | Name of the workflow |
| `dataset_path` | Yes | — | Path to the initial input dataset |
| `output_dir` | No | `.` | Root directory for per-step results |
| `path_from_workflow` | No | `true` | Resolve relative paths from the workflow file location |
| `rollback_on_job_failure` | No | `true` | Roll back to the previous step's state if a step fails |
| `create_job_snapshots` | No | `false` | Save a dataset snapshot before each step |
| `export_output` | No | `true` | Export the output dataset after each step |

### Step Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| `module` | Yes | — | Module to run (`DayAheadOrders`, `MarketClearing`, `PortfolioOptimisation`, `IntradayPriceForecast`) |
| `parameters_path` | Yes | — | Path to the module parameters file |
| `name` | No | module name | Custom name for the step |

!!! note "Duplicate step names"
    If two steps share the same name, Atlas automatically appends `_1`, `_2`, etc. to keep them unique.

---

## Run

### CLI

```bash
atlas workflow run workflow.yaml
```

To inspect the steps of a workflow file before running it:

```bash
atlas workflow list workflow.yaml
```

### Python

```python
from atlas import Workflow

workflow = Workflow.from_file("workflow.yaml")
workflow.execute()
```

### Programmatic

You can also build a workflow directly in Python, without a YAML file:

```python
from atlas import Workflow, WorkflowParameters
from atlas.orchestrator.workflow.job import Step

parameters = WorkflowParameters(
    name="day-ahead",
    dataset_path="./data/input/",
    output_dir="./results/",
    steps=[
        Step(module="DayAheadOrders", parameters_path="./parameters/day_ahead_orders.yml"),
        Step(module="MarketClearing", parameters_path="./parameters/market_clearing.yml"),
        Step(module="PortfolioOptimisation", parameters_path="./parameters/portfolio_optimisation.yml"),
    ],
)

workflow = Workflow(parameters=parameters)
workflow.execute()
```

This is useful for building workflows dynamically, for example when the list of steps depends on runtime conditions.

---

## Accessing Results

After execution, access the final output dataset:

```python
workflow.execute()

# Final dataset after all steps
result = workflow.get_output_dataset()

# Access results from the final dataset
for order in result.order.all():
    print(f"{order.name}: {order.accepted_power} MW")
```

To access the output of a specific step:

```python
# Access individual step results
for job in workflow.jobs:
    step_result = job.get_output_dataset()
    print(f"Step '{job.name}': {len(step_result.order.all())} orders")
```

---

## Directory Layout

A typical workflow project:

```
my-workflow/
├── workflow.yaml
├── data/
│   ├── input/              # Initial dataset (dataset_path)
│   └── output/             # Final dataset
├── parameters/
│   ├── day_ahead_orders.yml
│   ├── market_clearing.yml
│   └── portfolio_optimisation.yml
└── results/                # Per-step outputs (output_dir)
    ├── DayAheadOrders/
    ├── MarketClearing/
    └── PortfolioOptimisation/
```

When `path_from_workflow: true` (the default), all relative paths in `workflow.yaml` are resolved from the directory containing the workflow file — so you can move the whole folder without breaking paths.

---

## Advanced Options

### Rollback on Failure

With `rollback_on_job_failure: true` (default), if a step fails the dataset is restored to its state before that step. This prevents a partial run from leaving the dataset in an inconsistent state.

```yaml
rollback_on_job_failure: true  # safe default — always restore on failure
```

Set to `false` only if you want to inspect the dataset state at the point of failure.

### Step Snapshots

With `create_job_snapshots: true`, Atlas saves a copy of the dataset before each step. Useful for debugging — you can reload from any snapshot and re-run from that point.

```yaml
create_job_snapshots: true
```

Snapshots are saved in `output_dir/<step_name>/snapshot/`.

---

## See Also

- [Run a Module](running-modules.md): running a single module
- [Common Parameters](common-parameters.md): parameters shared by all modules
- [CLI reference](../cli.md): full command-line reference
- [Workflow API Reference](../api/workflow/workflow.md): full API documentation
