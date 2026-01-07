# User Guide Overview

## Introduction

The Market Clearing module is responsible for determining the market equilibrium by matching supply and demand across multiple market areas while respecting economic and network constraints.

## How to Use

The module follows ATLAS's standard `AbstractModule` pattern:

```python
from atlas.modules.market_clearing import MarketClearingModule

module = MarketClearingModule()
module.run(raw_data, raw_params)
```

Where:
- `raw_data`: Dictionary of business model objects (portfolios, equipment, market areas)
- `raw_params`: Parameter dictionary or path to JSON/YAML file

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
