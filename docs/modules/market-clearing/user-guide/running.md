# Running the Module

## Basic Usage

```python
from pathlib import Path

from atlas.io_utils.input_loader import InputLoader
from atlas.modules.market_clearing import MarketClearingModule

raw_data_path = Path("path/to/dataset")
raw_params_path = Path("path/to/parameters.yml")

mc_module = MarketClearingModule()
raw_data = InputLoader.from_directory(raw_data_path)
mc_module.run(raw_data, raw_params_path)
```

## Input Data Structure

Input data is basically a dictionary of business model objects by type, obtained by a call to `InputLoader.from_directory`:

```python
raw_data = {
    "market_area": [...],
    "control_block": [...],
    "order": [...],
    "order_coupling": [...],
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
    "solver": "XPRESS",
    "timestep": "PT1H"
}

# Or JSON file
module.run(raw_data, "config/parameters.json")
```

See [Parameters](input-data.md) for full list.


## Key Options

**How to change the type of Market Clearing** ? Set `market` to DayAhead / IntraDay / ...

**Solver**: Choose solver with `solver` parameter and configure `use_presolve`
