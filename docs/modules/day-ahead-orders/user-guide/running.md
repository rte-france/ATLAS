# Running the Module

## Basic Usage

See [Running Modules](../../../concepts/running-modules.md) for the standard ATLAS module execution pattern and parameter formats.

For common parameters (dates, solver, timestep, etc.), see [Common Parameters](../../../concepts/common-parameters.md).

## Module-Specific Parameters

This module primarily uses the common ATLAS parameters. All configuration is documented in [Parameters](input-data.md).

## Example Configuration

```python
from atlas import AtlasDataset, DayAheadOrdersModule

params = {
    # Common parameters
    "start_date": "2024-01-01T00:00:00",
    "end_date": "2024-01-02T00:00:00",
    "execution_date": "2023-12-31T12:00:00",
    "timestep": "PT1H",
    "solver_name": "XPRESS",
    "export_result": true
}

module = DayAheadOrdersModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
module.run(input_data, params)
```

See [Parameters](input-data.md) for the complete list of module-specific parameters.
