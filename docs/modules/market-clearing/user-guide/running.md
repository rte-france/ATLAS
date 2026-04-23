# Running the Module

## Basic Usage

See [Running Modules](../../running-modules.md) for the standard ATLAS module execution pattern and parameter formats.

For common parameters (dates, solver, timestep, etc.), see [Common Parameters](../../common-parameters.md). For module-specific parameters, see [Parameters](input-data.md).

## Example Configuration

```python
from atlas import AtlasDataset, MarketClearingModule

params = {
    "temporal": {
        "start_date": "2024-01-01T00:00:00",
        "end_date": "2024-01-02T00:00:00",
        "execution_date": "2023-12-31T12:00:00",
        "timestep": "PT1H",
    },
    "solver": {
        "solver_name": "XPRESS",
    },
    "output": {
        "export_result": True,
    },
    # Module-specific parameters
    "market": "DayAhead",
}

module = MarketClearingModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
module.run(input_data, params)
```
