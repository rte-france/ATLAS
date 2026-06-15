# Day-Ahead Orders Module

## Overview

Creates all market orders for the Day-Ahead market, for all equipments in the input dataset (including load, non-dispatchable, storage, hydraulic, wind, solar, and thermal orders). The order formulation at the portfolio level is currently not implemented in Atlas.

## Quick Start

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.day_ahead_orders import DayAheadOrdersModule

dataset = AtlasDataset.from_directory("path/to/dataset")
result = ModuleRun(
    module=DayAheadOrdersModule(),
    dataset=dataset,
    parameters="path/to/parameters.yml",
).run()
```

See [Running Modules](../running-modules.md) for execution details.

## Key Features

- **Multi-asset support**: Generates orders for all equipment types
- **Forecast-based**: Uses forecasts made at execution date
- **Flexible configuration**: Configurable order types and constraints

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
