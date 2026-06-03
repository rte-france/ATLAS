# Your First Simulation

This tutorial walks you through running a complete Atlas simulation from start to finish.

## Overview

In this tutorial, you will:

1. Understand the simulation workflow
2. Prepare input data in Atlas format
3. Configure simulation parameters
4. Run a Portfolio Optimisation simulation
5. Analyze the results

## What You'll Need

- Atlas installed ([see Installation](getting_started.md))
- A solver installed (OR-Tools comes by default, or [install Xpress](getting_started.md#available-solver))
- Sample dataset (instructions below)

## Understanding the general simulation pattern in ATLAS

Atlas simulations follow a general pattern:

```
Input Data → Module Parameters (or Workflow structure in that mode) → Simulation → Results
```

Each module processes:

- **AtlasDataset**: Static and time series data for market prices, demand, generation capacity, etc.
- **Parameters file**: YAML configuration defining simulation behavior
- **Output**: Optimized decisions, market outcomes, or generated orders

## Step 1: Prepare Your Dataset

Atlas uses a specific dataset format called **AtlasDataset**. For this tutorial, we'll use sample data.

### Test Dataset

For every module, you can find a small dataset in `tests/dataset/`.

For the full dataset format description, see [AtlasDataset examples](../examples/atlas_dataset.md).

## Step 2: Create a Parameters File

For a complete parameter reference, see:

- [Common Parameters](../modules/common-parameters.md)
- [Portfolio Optimisation Parameters](../modules/portfolio-optimisation/user-guide/parameters.md)


## Step 3: Run the Simulation

Execute the Portfolio Optimisation module:

```bash
atlas run portfolio_params.yaml \
  --module PortfolioOptimisation \
  --dataset ./atlas-dataset/
```

### What Happens During Execution

1. **Data Loading**: Atlas reads the input dataset
2. **Model Building**: Creates optimization model based on parameters
3. **Solving**: Runs the solver to find optimal decisions
4. **Output Generation**: Writes results to disk

## Step 4: Analyze the Results

Access results programmatically after the run:

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.portfolio_optimisation import PortfolioOptimisationModule

dataset = AtlasDataset.from_directory("./atlas-dataset/")
result = ModuleRun(
    module=PortfolioOptimisationModule(),
    dataset=dataset,
    parameters="portfolio_params.yaml",
).run()

# Access equipment results
for equipment in result.equipment:
    power_forecast = equipment.power.get_forecast(
        execution_date, start_date, end_date
    )
```

See [Results](../modules/portfolio-optimisation/user-guide/results.md) for the full output reference.

## Step 5: Run a Multi-Module Workflow

For realistic simulations, chain multiple modules together using a workflow:

Create `workflow.yaml`:

```yaml
name: "complete_market_simulation"
dataset_path: path/to/dataset
output_dataset_path: path/to/output/dataset
steps:
  - name: "generate_orders"
    module: "DayAheadOrders"
    parameters_path: "day_ahead_params.yaml"

  - name: "clear_market"
    module: "MarketClearing"
    parameters_path: "market_clearing_params.yaml"

  - name: "optimize_portfolio"
    module: "PortfolioOptimisation"
    parameters_path: "portfolio_params.yaml"

```

Run the workflow:

```bash
atlas run workflow.yaml --workflow
```

Learn more in the [Workflow documentation](../api/workflow/workflow.md).

### Getting Help

- Check [CLI Reference](../cli.md) for command details
- See [Examples](../examples/optimisation_model.md) for code samples
- Open an issue on [GitHub](https://github.com/rte-france/ATLAS/issues)

## Next Steps

Now that you've run your first simulation, explore:

- [Module-specific guides](../modules/portfolio-optimisation/user-guide/overview.md)
- [Advanced examples](../examples/atlas_dataset.md)
- [API Reference](../api/io/atlas_dataset.md) for programmatic usage
- [Contributing](../contributing.md) to Atlas development
