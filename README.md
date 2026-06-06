<div align="center">

# ATLAS

**Power market simulator for day-ahead, intraday, and reserve markets.**

Developed by [Artelys](https://www.artelys.com) for [RTE](https://www.rte-france.com)

[![CI](https://github.com/rte-france/ATLAS/actions/workflows/test.yml/badge.svg)](https://github.com/rte-france/ATLAS/actions)
[![codecov](https://codecov.io/gh/rte-france/ATLAS/branch/main/graph/badge.svg)](https://codecov.io/gh/rte-france/ATLAS)
![Python](https://img.shields.io/badge/python-3.13%2B-blue)
[![License](https://img.shields.io/github/license/rte-france/ATLAS)](LICENSE)

> **Status**: under active development — no stable release yet.

</div>

## Overview

ATLAS simulates electricity market mechanisms across the full trading horizon. It models the sequential decisions of market participants — from order formulation ahead of the auction to market clearing and portfolio optimisation — using a modular, configurable architecture.

Each **module** is an independent computation unit that reads from a shared dataset and produces structured changes applied by the orchestrator. Modules are chained into **workflows**, where the output of each step feeds into the next.

## Market Chains

Modules are grouped into market chains, each representing a full simulation cycle.

**Day-Ahead** — available

| Module | Description |
|---|---|
| **Day-Ahead Orders** | Generates market orders for all equipment types based on asset characteristics and cost structure. |
| **Market Clearing** | Determines market equilibrium by matching supply and demand across interconnected areas, under ATC or flow-based network constraints. |
| **Portfolio Optimisation** | Optimises energy asset portfolios (thermal, hydro, storage, solar, wind, load) to maximise profit under market conditions. |

**Intraday** — in development :rocket:

## Stack

- **Python 3.13+**, managed with [uv](https://docs.astral.sh/uv/)
- **OR-Tools** for optimisation, **Pydantic** for data models, **Polars** for data processing
- **Typer** for the CLI, **Ruff** for linting, **mypy** for type checking, **pytest** for tests

## Installation

Install [uv](https://docs.astral.sh/uv/#installation), then:

```bash
git clone https://github.com/rte-france/ATLAS.git && cd ATLAS && uv sync
```

## Quick Example

### 1. Build a dataset

```python
from atlas import AtlasDataset, ControlBlock, MarketArea, Node, Portfolio, Thermal
from atlas.math.timeseries import Timeseries

cb = ControlBlock(name="cb_fr")
area = MarketArea(name="fr", control_block=cb)
node = Node(name="node_fr", control_block=cb, market_area=area)
portfolio = Portfolio(name="gen_fr", control_block=cb, market_area=area)

variable_cost = Timeseries.from_index(
    start_date="2024-01-01 00:00:00",
    frequency="1h",
    end_date="2024-01-02 00:00:00",
    default_value=45.0,
)

nuclear = Thermal(
    name="fr_nuclear",
    node=node,
    portfolio=portfolio,
    installed_capacity=1584.0,
    variable_cost=variable_cost,
)

dataset = AtlasDataset(
    control_block=[cb],
    market_area=[area],
    node=[node],
    portfolio=[portfolio],
    thermal=[nuclear],
)
dataset.to_directory("./data/input/")
```

### 2. Configure parameters

```yaml
# parameters.yaml
temporal:
  start_date: "2024-01-01 00:00:00"
  end_date: "2024-01-02 00:00:00"
  execution_date: "2023-12-31 12:00:00"
  timestep: "PT1H"
solver:
  solver_name: "SCIP"
load_price: 3000
```

### 3. Run a module

```bash
atlas run parameters.yaml \
  --module DayAheadOrders \
  --dataset ./data/input/
```

Or from Python:

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.day_ahead_orders import DayAheadOrdersModule

dataset = AtlasDataset.from_directory("./data/input/")
result = ModuleRun(
    module=DayAheadOrdersModule(),
    dataset=dataset,
    parameters="parameters.yaml",
).run()
```

### 4. Run a full day-ahead workflow

```yaml
# workflow.yaml
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

```bash
atlas run workflow.yaml --workflow
```

## Documentation

Full documentation: [rte-atlas.readthedocs.io](https://rte-atlas.readthedocs.io)

## Contributing

See [CONTRIBUTING](docs/contributing.md).

## Changelog

See [CHANGELOG](docs/changelog.md).

## Authors

See [AUTHORS](docs/authors.md).
