# AtlasDataset Examples

The `AtlasDataset` is the main data container in Atlas. It stores and provides typed access to all business model objects alongside their time-varying data.

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
index  = pd.date_range("2024-01-01", periods=8760, freq="h", tz="UTC")
values = [120.0] * 8760  # constant 120 MWh/h inflows (example)
inflows_ts = Timeseries.from_values(index=index, values=values, name="inflows")

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

index        = pd.date_range("2024-01-01", periods=8760, freq="h", tz="UTC")
availability = Timeseries.from_values(index=index, values=np.random.uniform(0, 1, 8760).tolist(), name="availability")

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
