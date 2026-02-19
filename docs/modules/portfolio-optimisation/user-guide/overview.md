# User Guide Overview

## Introduction

The Portfolio Optimisation module optimizes energy portfolios to determine optimal dispatch strategies for thermal, hydro, solar, wind, storage, and load assets.

## How to Use

The module follows Atla's standard `AbstractModule` pattern, run it simply by calling `run` method:

```python
from atlas import AtlasDataset, PortfolioOptimisationModule

module = PortfolioOptimisationModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
module.run(input_data, "path/to/parameters.yml")
```

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
