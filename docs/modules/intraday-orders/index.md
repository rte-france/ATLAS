# Intraday Orders Module

## Overview

Creates all market orders for the Intraday market, for every equipment in the input dataset (load, non-dispatchable, storage, hydraulic, wind, solar, and thermal). Unlike the Day-Ahead module, intraday orders are **adjustment orders**: they express how each unit wants to move away from its already-cleared engagement (Day-Ahead plus all prior intraday sessions) towards a new intraday target planning. Order formulation is heuristic — no optimisation problem is solved.

## Quick Start

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.intraday_orders.module import IntradayOrdersModule

dataset = AtlasDataset.from_directory("path/to/dataset")
result = ModuleRun(
    module=IntradayOrdersModule(),
    dataset=dataset,
    parameters="path/to/parameters.yml",
).run()
```

See [Running Modules](../running-modules.md) for execution details.

## Key Features

- **Adjustment-based**: Orders capture the delta between the cleared engagement and the new intraday target planning
- **Multi-asset support**: Generates orders for all equipment types
- **Forecast-based**: Uses forecasts retrieved at `execution_date`
- **Cumulative engagement tracking**: Accumulates submitted volumes across successive intraday sessions

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
