# User Guide Overview

## Introduction

The Portfolio Optimisation module optimizes energy portfolios to determine optimal dispatch strategies for thermal, hydro, solar, wind, storage, and load assets.

## How to Use

The module follows Atla's standard `AbstractModule` pattern, run it simply by calling `run` method:

```python
module = PortfolioOptimisationModule()
module.run(input_data: dict[str, list[BusinessModel]], parameters: PortfolioOptimisationParameters)
```

Where:

- `raw_data`: Dictionary of business model objects (portfolios, equipment, market areas)
- `raw_params`: Parameter dictionary or path to JSON/YAML file

## Module Workflow

The `run()` method executes:

1. **Import Parameters**: Load `PortfolioOptimisationParameters`
2. **Import Data**: Convert to `PortfolioOptimisationInputDataset`
3. **Validate**: Check timestep consistency
4. **Execute**: Run optimization for each portfolio
5. **Export**: Update equipment `power` and portfolio `imbalance` (if `export_result=True`)

Results are stored directly in the business model objects.

## Next Steps

- [Parameters](input-data.md): Configuration options
- [Running](running.md): Execution details
- [Results](results.md): Accessing outputs
