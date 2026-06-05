# AtlasDataset Examples

The `AtlasDataset` is the main data container in Atlas. It stores and provides typed access to all business model objects alongside their time-varying data.

## Directory Structure

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

### Objects Directory

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

### Timeseries Directory

Contains subdirectories per object type, with Parquet/CSV files storing time-indexed data:

- One file per object (e.g., `fr_nuclear.parquet` for a thermal unit)
- Multiple attributes stored using an `attribute` column as a categorical filter
- Common attributes: generation profiles, availability, costs over time

Example `timeseries/thermal/fr_nuclear.csv`:

| time | attribute | value |
|------|-----------|-------|
| 2024-01-01 00:00:00 | availability | 0.95 |
| 2024-01-01 01:00:00 | availability | 0.95 |
| 2024-01-01 00:00:00 | marginal_cost | 45.2 |
| 2024-01-01 01:00:00 | marginal_cost | 45.5 |

The `attribute` column acts as a filter — filtering by `attribute == "availability"` gives you the availability timeseries.

### Matrix Directories

**scenario_matrix/**: Multi-scenario stochastic data (e.g., uncertain inflows, demand scenarios). Each scenario column represents a possible realization.

| time | attribute | scenario_0 | scenario_1 | scenario_2 |
|------|-----------|------------|------------|------------|
| 2024-01-01 00:00:00 | inflows | 125.3 | 98.7 | 156.2 |
| 2024-01-01 01:00:00 | inflows | 128.1 | 102.4 | 159.8 |

**forecasting_matrix/**: Forecast data with multiple forecast horizons. Each column is indexed by an execution date, i.e. the date at which the information contained in the column is revealed to market actors.

| time | attribute | 2026-01-01 00:00:00 | 2026-01-01 01:00:00 |
|------|-----------|---------------------|---------------------|
| 2024-01-01 00:00:00 | price | 52.3 | 51.8 |
| 2024-01-01 01:00:00 | price | 48.7 | 49.2 |

### Supported File Formats

- **Parquet** (recommended): Efficient binary format for large datasets
- **CSV**: Human-readable, semicolon-separated

## Loading a Dataset

```python
from atlas import AtlasDataset

# Eager loading — all data loaded immediately into memory
dataset = AtlasDataset.from_directory("data/atlas-dataset/")

# Lazy loading — files are read on first access (recommended for large datasets)
dataset = AtlasDataset.from_directory("data/atlas-dataset/", lazy=True)

# From a pickle snapshot
dataset = AtlasDataset.from_pickle("snapshots/dataset.pkl")
```

## Accessing Objects

```python
# Get all objects of a type
thermals = dataset.thermal.all()
hydros   = dataset.hydro.all()

# Generic accessor
thermals = dataset.get_items_by_type("thermal")

# Get a specific object by name
fr_nuclear = dataset.thermal.get("fr_nuclear")
fr_area    = dataset.market_area.get("fr")

# Iterate over multiple types at once
for unit in dataset.iter_by_types("thermal", "hydro", "wind"):
    print(f"{unit.name} → node: {unit.node.name}, portfolio: {unit.portfolio.name}")
```

## Exporting Data

```python
# Export to directory (standard AtlasDataset format)
dataset.to_directory("output/atlas-dataset/")

# Export to pickle (fast round-trip for intermediate results)
dataset.to_pickle("snapshots/dataset.pkl")

# Export to dict (useful for inspection or custom serialization)
data_dict = dataset.to_dict()
```

## Creating a Dataset from Scratch

Build a full dataset by constructing objects in dependency order. See the [data model](../data-model.md) for the hierarchy.

```python
from atlas import (
    AtlasDataset,
    ControlBlock,
    MarketArea,
    Node,
    Portfolio,
    Thermal,
    Hydro,
    Wind,
    Solar,
)

# 1. Top-level: ControlBlock (no dependencies)
cb_fr = ControlBlock(name="cb_fr")
cb_de = ControlBlock(name="cb_de")

# 2. MarketArea depends on ControlBlock
area_fr = MarketArea(name="fr", control_block=cb_fr)
area_de = MarketArea(name="de", control_block=cb_de)

# 3. Node depends on ControlBlock + MarketArea
node_fr = Node(name="node_fr", control_block=cb_fr, market_area=area_fr)
node_de = Node(name="node_de", control_block=cb_de, market_area=area_de)

# 4. Portfolio depends on ControlBlock + MarketArea
portfolio_fr = Portfolio(name="generator_fr", control_block=cb_fr, market_area=area_fr)
portfolio_de = Portfolio(name="generator_de", control_block=cb_de, market_area=area_de)

# 5. Equipment depends on Node + Portfolio
nuclear = Thermal(name="fr_nuclear", node=node_fr, portfolio=portfolio_fr, installed_capacity=1584.0)
coal    = Thermal(name="de_coal",    node=node_de, portfolio=portfolio_de, installed_capacity=500.0)

# Assemble the dataset
dataset = AtlasDataset(
    control_block=[cb_fr, cb_de],
    market_area=[area_fr, area_de],
    node=[node_fr, node_de],
    portfolio=[portfolio_fr, portfolio_de],
    thermal=[nuclear, coal],
)
```

## Adding New Objects to an Existing Dataset

### Add a new thermal unit

```python
from atlas import AtlasDataset, Thermal

dataset = AtlasDataset.from_directory("data/atlas-dataset/")

# Reuse existing node and portfolio (must already exist in the dataset)
node_fr      = dataset.node.get("node_fr")
portfolio_fr = dataset.portfolio.get("generator_fr")

new_gas = Thermal(
    name="fr_gas_peaker",
    node=node_fr,
    portfolio=portfolio_fr,
    installed_capacity=300.0,
    minimum_time_on="PT2H",   # ISO 8601 duration
    minimum_time_off="PT1H",
)

dataset.thermal.add(new_gas)
dataset.to_directory("data/atlas-dataset/")
```

### Add a new hydro plant with timeseries

```python
from atlas import AtlasDataset, Hydro
from atlas.math.timeseries import Timeseries
import pandas as pd

dataset = AtlasDataset.from_directory("data/atlas-dataset/")

node_fr      = dataset.node.get("node_fr")
portfolio_fr = dataset.portfolio.get("generator_fr")

# Build inflows timeseries
inflows_ts = Timeseries.from_values(
    start_date="2024-01-01 00:00:00",
    frequency="1h"
    values=[120.0] * 8760 ,# constant 120 MWh/h inflows (example)
    timezone="UTC")

hydro = Hydro(
    name="fr_mountain_hydro",
    node=node_fr,
    portfolio=portfolio_fr,
    inflows=inflows_ts,
    inflow_frequency="Daily",
)

dataset.hydro.add(hydro)
dataset.to_directory("data/atlas-dataset/")
```

### Add a wind farm

```python
from atlas import AtlasDataset, Wind
from atlas.math.timeseries import Timeseries
import pandas as pd
import numpy as np

dataset = AtlasDataset.from_directory("data/atlas-dataset/")

node_de      = dataset.node.get("node_de")
portfolio_de = dataset.portfolio.get("generator_de")

availability = Timeseries.from_values(
    start_date="2024-01-01 00:00:00",
    frequency="1h"
    values=np.random.uniform(0, 1, 8760).tolist(),
    timezone="UTC")

wind_farm = Wind(
    name="de_offshore_wind",
    node=node_de,
    portfolio=portfolio_de,
    variable_cost=None,
)
# Attach timeseries after construction
wind_farm.variable_cost = availability

dataset.wind.add(wind_farm)
dataset.to_directory("data/atlas-dataset/")
```

### Add a new market area and its node

```python
from atlas import AtlasDataset, ControlBlock, MarketArea, Node

dataset = AtlasDataset.from_directory("data/atlas-dataset/")

# Add a new control block for Spain
cb_es   = ControlBlock(name="cb_es")
area_es = MarketArea(name="es", control_block=cb_es)
node_es = Node(name="node_es", control_block=cb_es, market_area=area_es)

dataset.control_block.add(cb_es)
dataset.market_area.add(area_es)
dataset.node.add(node_es)

dataset.to_directory("data/atlas-dataset/")
```

## Updating an Existing Object

```python
dataset = AtlasDataset.from_directory("data/atlas-dataset/")

nuclear = dataset.thermal.get("fr_nuclear")
nuclear.installed_capacity = 1200.0   # update in-place

dataset.to_directory("data/atlas-dataset/")
```

## Removing an Object

```python
dataset = AtlasDataset.from_directory("data/atlas-dataset/")

dataset.thermal.remove("fr_nuclear")

dataset.to_directory("data/atlas-dataset/")
```

## Filtering Equipment

`filter_equipments` returns a new dataset containing only the named equipment units. All other object types (market areas, nodes, portfolios…) are preserved.

```python
dataset = AtlasDataset.from_directory("data/atlas-dataset/")

# Keep only these two units across all equipment types
subset = dataset.filter_equipments(["fr_nuclear", "fr_mountain_hydro"])

# None or empty list → full copy, nothing filtered
full_copy = dataset.filter_equipments(None)
```

The returned dataset is a deep copy — modifying it does not affect the original.

## Filtering Zones

`filter_zones` keeps only objects that belong to a given set of control blocks (TSO zones). This is useful for running a simulation on a geographic sub-selection.

```python
dataset = AtlasDataset.from_directory("data/atlas-dataset/")

# Keep only the French zone (objects whose control_block == "cb_fr")
fr_dataset = dataset.filter_zones(["cb_fr"])

# Keep French and German zones together
fr_de_dataset = dataset.filter_zones(["cb_fr", "cb_de"])
```

By default, cross-border interconnections are only kept when **both** endpoints are in the selected zones (isolated network). Pass `include_external_borders=True` to also retain borders that connect a selected zone to an external one:

```python
# Include borders where at least one side is in the selected zone
fr_dataset_open = dataset.filter_zones(["cb_fr"], include_external_borders=True)
```

Raises `ValueError` if any control block name does not exist in the dataset.

## Iterating Over All Equipment

`iter_by_equipments` yields every equipment object regardless of its concrete type:

```python
dataset = AtlasDataset.from_directory("data/atlas-dataset/")

for unit in dataset.iter_by_equipments():
    print(f"{type(unit).__name__}: {unit.name} — node: {unit.node.name}")
```

To iterate over a subset of types, use `iter_by_types` instead:

```python
for unit in dataset.iter_by_types("thermal", "hydro"):
    print(unit.name, unit.portfolio.name)
```

For more information, see the [API Reference](../api/io/atlas_dataset.md) and the [Data Model](../data-model.md).
