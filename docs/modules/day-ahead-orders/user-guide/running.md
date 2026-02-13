# Running the Module

## Basic Usage

```python
from pathlib import Path

from atlas import InputLoader
from atlas.modules.day_ahead_orders.module import DayAheadOrdersModule

raw_data_path = Path("path/to/dataset")
raw_params_path = Path("path/to/parameters.yml")

mc_module = DayAheadOrdersModule()
raw_data = InputLoader.from_directory(raw_data_path)
mc_module.run(raw_data, raw_params_path)  # type:ignore [arg-type]
```

## Input Data Structure

Input data is basically a dictionary of business model objects by type, obtained by a call to `InputLoader.from_directory`:

```python
raw_data = {
    "portfolio": [portfolio1, portfolio2, ...],
    "thermal": [thermal_unit1, ...],
    "hydro": [hydro_unit1, ...],
    "storage": [storage1, ...],
    "solar": [solar1, ...],
    "wind": [wind1, ...],
    "load": [load1, ...],
    "node": [...],
    "other_non_dispatchable": [...],
    "market_area": [...],
    "market_border": [...],
    "control_block": [...]
}
```

## Parameters

Provide as dictionary or file path:

```python
# Dictionary
params = {
    "start_date": "2024-01-01T00:00:00",
    "end_date": "2024-01-02T00:00:00",
    "execution_date": "2023-12-31T12:00:00",
    "export_result": true,
    "solver_name": "XPRESS",
    "timestep": "PT1H"
}

# Or JSON file
module.run(raw_data, "config/parameters.json")
```

See [Parameters](input-data.md) for full list.

## Key Options

**Solver**: Choose solver with `solver_name` parameter and configure `solver_timeout`, `solver_duality_gap`, `use_presolve`
