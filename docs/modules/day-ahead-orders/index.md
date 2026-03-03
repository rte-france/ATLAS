# Day-Ahead Orders Module

## Overview

Computes all market orders based on equipment in the input dataset, including load, non-dispatchable, storage, hydraulic, wind, solar, and thermal orders.

## Quick Start

```python
from atlas import AtlasDataset, DayAheadOrdersModule

module = DayAheadOrdersModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
module.run(input_data, "path/to/parameters.yml")
```

See [Running Modules](../../concepts/running-modules.md) for execution details.

## Key Features

- **Multi-asset support**: Generates orders for all equipment types
- **Forecast-based**: Uses forecasts made at execution date
- **Flexible configuration**: Configurable order types and constraints

## Documentation

### User Guide
- [Overview](user-guide/overview.md): Module-specific introduction
- [Parameters](user-guide/input-data.md): Module-specific parameters
- [Running](user-guide/running.md): Execution details

### Common Documentation
- [Module Pattern](../../concepts/module-pattern.md): ATLAS module architecture
- [Common Parameters](../../concepts/common-parameters.md): Shared configuration options
- [Running Modules](../../concepts/running-modules.md): General execution guide

### Developer Reference
- [Architecture](developer/architecture.md): Module design and structure
