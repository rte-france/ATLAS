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
| `module` | Yes | — | Module to run (`DayAheadOrders`, `MarketClearing`, `PortfolioOptimisation`, `IntradayPriceForecast`) |
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

!!! info "Parameter files format"
    Each `parameters_path` file in `parameters/` must follow the YAML format defined by the corresponding module.
    See the **Parameters** section in each module's user guide for the expected structure and available fields:

    - [Day-Ahead Orders parameters](../modules/day-ahead-orders/user-guide/parameters.md)
    - [Market Clearing parameters](../modules/market-clearing/user-guide/parameters.md)
    - [Portfolio Optimisation parameters](../modules/portfolio-optimisation/user-guide/parameters.md)
    - [Intraday Price Forecast parameters](../modules/intraday-price-forecast/user-guide/parameters.md)

When `path_from_workflow: true` (the default), all relative paths in `workflow.yaml` are resolved from the directory containing the workflow file — so you can move the whole folder without breaking paths.

## See Also

- [Running Modules in Python](running-modules.md): how to run a single module
- [Common Parameters](common-parameters.md): parameters shared by all modules
- [Workflow API Reference](../api/workflow/workflow.md): full API documentation
