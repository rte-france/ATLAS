# Running the Module

## Basic Usage

See [Running Modules](../../../concepts/running-modules.md) for the standard ATLAS module execution pattern and parameter formats.

For common parameters (dates, solver, timestep, etc.), see [Common Parameters](../../../concepts/common-parameters.md).

## Module-Specific Parameters

This module adds the following parameters beyond the common ones:

### Optimization Mode

**`is_portfolio_bidding`** (boolean, default: `true`):
- `true`: Optimize entire portfolios with imbalance penalties and coordination
- `false`: Optimize each unit independently

### Equipment Selection

**`excluded_market_areas`** (list of strings): Market areas to exclude from optimization

**`excluded_technologies`** (list of strings): Technology types to exclude (e.g., `["THERMAL", "HYDRO"]`)

**`excluded_thermal_strategy`** (list of strings): Thermal strategies to exclude (e.g., `["MUST_RUN"]`)


## Example Configuration

```python
from atlas import AtlasDataset, PortfolioOptimisationModule

params = {
    # Common parameters
    "start_date": "2024-01-01T00:00:00",
    "end_date": "2024-01-02T00:00:00",
    "execution_date": "2023-12-31T12:00:00",
    "timestep": "PT1H",
    "solver_name": "XPRESS",
    "export_result": true,

    # Module-specific parameters
    "is_portfolio_bidding": true,
    "excluded_technologies": ["load"]
}

module = PortfolioOptimisationModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
module.run(input_data, params)
```

See [Parameters](input-data.md) for the complete list of module-specific parameters.
