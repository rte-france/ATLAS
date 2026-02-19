# User Guide Overview

## Introduction

The Market Clearing module is responsible for determining the market equilibrium by matching supply and demand across multiple market areas while respecting economic and network constraints.

## How to Use

The module follows ATLAS's standard `AbstractModule` pattern:

```python
from atlas import AtlasDataset, MarketClearingModule

module = MarketClearingModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
module.run(input_data, "path/to/parameters.yml")
```


## Module Workflow

The `run()` method executes:

1. **Import Parameters**: Load `MarketClearingParameters`
2. **Import Data**: Convert to `MarketClearingInputDataset`
3. **Validate**: Check timestep consistency
4. **Execute**: Run all phases and result
5. **Export**: Update prices of equipments/portfolios and flow

Results are stored directly in the business model objects.

## Next Steps

- [Parameters](input-data.md): Configuration options
- [Running](running.md): Execution details
