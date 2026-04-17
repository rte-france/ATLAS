# Workflows

A workflow chains multiple modules sequentially, where the output dataset of each step becomes the input of the next.

## Workflow Configuration File

A workflow is defined in a YAML file:

```yaml
name: my-workflow
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

### Top-level Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| `name` | No | `null` | Name of the workflow |
| `dataset_path` | Yes | — | Path to the initial input dataset |
| `output_dataset_path` | Yes | — | Path where the final output dataset is written |
| `output_dir` | No | `.` | Root directory for per-step results |
| `path_from_workflow` | No | `true` | If `true`, resolve relative paths from the workflow file location |
| `rollback_on_job_failure` | No | `true` | Roll back the dataset to the previous step state if a step fails |
| `create_job_snapshots` | No | `false` | Save a dataset snapshot before each step (useful for debugging) |
| `export_output` | No | `true` | Export the output dataset after each step |

### Step Parameters

Each entry under `steps` defines one execution unit:

| Parameter | Required | Default | Description |
|---|---|---|---|
| `module` | Yes | — | Module to run (`DayAheadOrders`, `MarketClearing`, `PortfolioOptimisation`) |
| `parameters_path` | Yes | — | Path to the module parameters file |
| `name` | No | module name | Custom name for the step |

!!! note "Duplicate step names"
    If two steps share the same name (or the same module without a custom name), Atlas automatically appends `_1`, `_2`, etc. to keep names unique.

## Running a Workflow

### CLI

```bash
atlas run workflow.yaml --workflow
```

### Python

```python
from atlas import Workflow

workflow = Workflow.from_file("workflow.yaml")
workflow.execute()

# Access the final output dataset
output = workflow.get_output_dataset()
```

## Directory Layout

A typical workflow project looks like this:

```
my-workflow/
├── workflow.yaml
├── data/
│   ├── input/          # Initial dataset (dataset_path)
│   └── output/         # Final dataset (output_dataset_path)
├── parameters/
│   ├── day_ahead_orders.yml
│   ├── market_clearing.yml
│   └── portfolio_optimisation.yml
└── results/            # Per-step outputs (output_dir)
    ├── DayAheadOrders/
    ├── MarketClearing/
    └── PortfolioOptimisation/
```

When `path_from_workflow: true` (the default), all relative paths in `workflow.yaml` are resolved from the directory containing the workflow file — so you can move the whole folder without breaking paths.

## See Also

- [Running Modules in Python](running-modules.md): how to run a single module
- [Common Parameters](common-parameters.md): parameters shared by all modules
- [Workflow API Reference](../api/workflow/workflow.md): full API documentation
