# Running the Module

## Basic Usage

```python
from atlas import AtlasDataset, MarketClearingModule

module = MarketClearingModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
module.run(input_data, "path/to/parameters.yml")
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
module.run(input_data, "config/parameters.json")
```

See [Parameters](input-data.md) for full list.


## Key Options

**How to change the type of Market Clearing** ? Set `market` to DayAhead / IntraDay / ...

**Solver**: Choose solver with `solver` parameter and configure `use_presolve`
