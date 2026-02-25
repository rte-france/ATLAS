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

- Atlas installed ([see Installation](../getting_started.md))
- A solver installed (OR-Tools comes by default, or [install Xpress](../getting_started.md#available-solver))
- Sample dataset (instructions below)

## Understanding the Workflow

Atlas simulations follow a general pattern:

```
Input Data → Module Parameters → Simulation → Results
```

Each module processes:

- **AtlasDataset**: Time series data for market prices, demand, generation capacity, etc.
- **Parameters file**: YAML configuration defining simulation behavior
- **Output**: Optimized decisions, market outcomes, or generated orders

## Step 1: Prepare Your Dataset

Atlas uses a specific dataset format called **AtlasDataset**. For this tutorial, we'll use sample data.

### Dataset Structure

An AtlasDataset follows a specific directory structure that separates business objects from their associated time-varying data:

```
atlas-dataset/
├── objects/             # Business model definitions (CSV)
│   ├── market_area.csv
│   ├── node.csv
│   ├── portfolio.csv
│   ├── thermal.csv
│   ├── hydro.csv
│   ├── wind.csv
│   ├── solar.csv
│   └── ...
├── timeseries/          # Time-indexed data (Parquet/CSV)
│   ├── thermal/
│   │   └── unit_name.parquet
│   ├── hydro/
│   │   └── plant_name.parquet
│   └── market_area/
│       └── area_name.parquet
├── scenario_matrix/     # Multi-scenario data (Parquet/CSV)
│   ├── thermal/
│   │   └── unit_name.parquet
│   └── hydro/
│       └── plant_name.parquet
└── forecasting_matrix/  # Forecast data (Parquet/CSV)
    ├── market_area/
    │   └── area_name.parquet
    └── thermal/
        └── unit_name.parquet
```

#### Objects Directory

Contains CSV files (semicolon-separated by default) defining business model objects:

- **thermal.csv**: Thermal generation units with attributes like capacity, ramp rates, costs
- **hydro.csv**: Hydroelectric plants with reservoir characteristics
- **market_area.csv**: Market area definitions with price forecasts
- **node.csv**: Network nodes
- **portfolio.csv**: Portfolio definitions grouping assets

Example `thermal.csv`:

| name | node | portfolio | installed_capacity | minimum_time_on | strategy |
|------|------|-----------|-------------------|-----------------|----------|
| fr_nuclear | fr | generator_fr | 1584.0 | PT1H | Intermediate |
| de_coal | de | generator_de | 500.0 | P1D | Base |

#### Timeseries Directory

Contains subdirectories per object type, with Parquet/CSV files storing time-indexed data:

- One file per object (e.g., `fr_nuclear.parquet` for a thermal unit)
- Multiple attributes stored using an `attribute` column as a categorical filter
- Common attributes: generation profiles, availability, costs over time

Example `timeseries/thermal/fr_nuclear.csv`:

| time | attribute | value |
|------|-----------|-------|
| 2024-01-01 00:00:00 | availability | 0.95 |
| 2024-01-01 01:00:00 | availability | 0.95 |
| 2024-01-01 02:00:00 | availability | 0.93 |
| 2024-01-01 00:00:00 | marginal_cost | 45.2 |
| 2024-01-01 01:00:00 | marginal_cost | 45.5 |
| 2024-01-01 02:00:00 | marginal_cost | 46.1 |

The `attribute` column acts as a filter - filtering by `attribute == "availability"` gives you the availability timeseries.

#### Matrix Directories

**scenario_matrix/**: Multi-scenario stochastic data (e.g., uncertain inflows, demand scenarios)

Example `scenario_matrix/hydro/mountain_hydro.csv`:

| time | attribute | scenario_0 | scenario_1 | scenario_2 |
|------|-----------|------------|------------|------------|
| 2024-01-01 00:00:00 | inflows | 125.3 | 98.7 | 156.2 |
| 2024-01-01 01:00:00 | inflows | 128.1 | 102.4 | 159.8 |
| 2024-01-01 02:00:00 | inflows | 130.5 | 105.1 | 163.4 |

Each scenario column represents a possible realization of uncertain inflows.

**forecasting_matrix/**: Forecast data with multiple forecast horizons (e.g., price forecasts, demand forecasts)

Example `forecasting_matrix/market_area/fr.csv`:

| time | attribute | 2026-01-01 00:00:00 | 2026-01-01 01:00:00 | 2026-01-01 02:00:00 |
|------|-----------|-------------|-------------|-------------|
| 2024-01-01 00:00:00 | price | 52.3 | 51.8 | 50.5 |
| 2024-01-01 01:00:00 | price | 48.7 | 49.2 | 48.9 |
| 2024-01-01 02:00:00 | price | 45.2 | 46.1 | 46.8 |

Each forecast column represents predictions at different forecast horizons (h0 = current hour, h1 = next hour, etc.).

#### Supported File Formats

- **Parquet** (recommended): Efficient binary format for large datasets
- **CSV**: Human-readable, semicolon-separated

Learn more in the [AtlasDataset documentation](../api/io/atlas_dataset.md) and [examples](../examples/atlas_dataset.md).

## Step 2: Create a Parameters File

For a complete parameter reference, see:

- [Common Parameters](../modules/common-parameters.md)
- [Portfolio Optimisation Parameters](../modules/portfolio-optimisation/user-guide/input-data.md)

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


## Step 5: Run a Multi-Module Workflow

For realistic simulations, chain multiple modules together using a workflow:

Create `workflow.yaml`:

```yaml
name: "complete_market_simulation"

steps:
  - name: "generate_orders"
    module: "DayAheadOrders"
    parameters: "day_ahead_params.yaml"

  - name: "clear_market"
    module: "MarketClearing"
    parameters: "market_clearing_params.yaml"

  - name: "optimize_portfolio"
    module: "PortfolioOptimisation"
    parameters: "portfolio_params.yaml"

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
