# Market Clearing Module

## Overview

Determines market equilibrium by matching supply and demand across multiple market areas while respecting economic and network constraints.

## Quick Start

```python
from atlas import AtlasDataset, MarketClearingModule

module = MarketClearingModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
module.run(input_data, "path/to/parameters.yml")
```

See [Running Modules](../../concepts/running-modules.md) for execution details.

## Key Outputs

- **Accepted quantities**: For each market order
- **Market clearing prices**: Per market area
- **Cross-border exchanges**: Between market areas

## Key Features

- **Multi-area support**: Handles multiple interconnected market areas
- **Network constraints**: Respects transmission capacity limits
- **Economic optimization**: Maximizes social welfare

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
