# BSP Balancing Orders Module

## Overview

Creates the balancing energy orders submitted by Balancing Service Providers (BSPs) on a balancing activation market (RR or mFRR), for every eligible equipment in the input dataset (load, wind, solar, storage, hydraulic and thermal). Each order offers the upward or downward flexibility a unit still has around its forecasted schedule, once its procured reserves are set aside. Order formulation is heuristic — no optimisation problem is solved.

## Quick Start

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.balancing_market_bsp_orders.module import BSPBalancingOrdersModule

dataset = AtlasDataset.from_directory("path/to/dataset")
result = ModuleRun(
    module=BSPBalancingOrdersModule(),
    dataset=dataset,
    parameters="path/to/parameters.yml",
).run()
```

See [Running Modules](../running-modules.md) for execution details.

## Key Features

- **RR or mFRR**: Formulates orders for the `RRActivation` or `MFRRActivation` product
- **Reserve-aware**: Volumes already procured on other reserve products are removed from the offered flexibility
- **Technical constraints**: Setup delay, maximum gradient, storage levels, daily energy limits and thermal on/off dynamics are taken into account
- **Forecast-based**: Uses forecasts retrieved at `execution_date`

## Documentation

### User Guide
- [Overview](user-guide/overview.md): Module-specific introduction
- [Parameters](user-guide/parameters.md): Module-specific parameters
- [Input Objects](user-guide/input-objects.md): Required input data and attributes
- [Results](user-guide/results.md): Accessing outputs

### Common Documentation
- [Module Pattern](../module-pattern.md): ATLAS module architecture
- [Common Parameters](../common-parameters.md): Shared configuration options
- [Running Modules](../running-modules.md): General execution guide

### Developer Reference
- [Architecture](developer/architecture.md): Module design and structure
