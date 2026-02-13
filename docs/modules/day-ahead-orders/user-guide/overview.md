# User Guide Overview

## Introduction

This module computes all **Order** instances based on the **Equipment** instances found in the input dataset, between ***start date*** and ***end date***.
The data used for the calculation is based on a forecast made at ***execution date***.

## How to Use

The module follows Atlas standard `AbstractModule` pattern, run it simply by calling `run` method:

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

Where:

- `raw_data_path`: Path to the dataset to use
- `raw_data`: Dictionary of business model objects (portfolios, equipment, market areas)
- `raw_params_path`: Parameter dictionary or path to JSON/YAML file

## Module Workflow

The `run()` method executes:

1. **Import Parameters**: Load `DayAheadOrdersParameters`
2. **Import Data**: Convert to `DayAheadOrdersInputDataset`
3. **Validate**: Check timestep consistency
4. **Execute**: Run all steps

Results are stored directly in the business model objects.

## Next Steps

- [Parameters](input-data.md): Configuration options
- [Running](running.md): Execution details
