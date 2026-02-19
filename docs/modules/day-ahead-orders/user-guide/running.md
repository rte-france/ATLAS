# Running the Module

## Basic Usage

```python
from atlas import AtlasDataset, DayAheadOrdersModule

module = DayAheadOrdersModule()
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
    "solver_name": "XPRESS",
    "timestep": "PT1H"
}

# Or JSON file
module.run(raw_data, "config/parameters.json")
```

See [Parameters](input-data.md) for full list.

## Key Options

**Solver**: Choose solver with `solver_name` parameter and configure `solver_timeout`, `solver_duality_gap`, `use_presolve`
