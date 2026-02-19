# User Guide Overview

## Introduction

This module computes all **Order** instances based on the **Equipment** instances found in the input dataset, between ***start date*** and ***end date***.
The data used for the calculation is based on a forecast made at ***execution date***.

## How to Use

The module follows Atlas standard `AbstractModule` pattern, run it simply by calling `run` method:

```python
from atlas import AtlasDataset, DayAheadOrdersModule

module = DayAheadOrdersModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
module.run(input_data, "path/to/parameters.yml")
```

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
