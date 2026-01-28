# User Guide Overview

## Introduction

The Market Clearing module is responsible for determining the market equilibrium by matching supply and demand across multiple market areas while respecting economic and network constraints.

## How to Use

The module follows ATLAS's standard `AbstractModule` pattern:

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

Where:
- `raw_data_path`: Path to the dataset to use
- `raw_data`: Dictionary of business model objects (portfolios, equipment, market areas)
- `raw_params_path`: Parameter dictionary or path to JSON/YAML file

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
