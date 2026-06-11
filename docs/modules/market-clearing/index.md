# Market Clearing Module

## Overview

Determines market equilibrium by matching supply and demand across multiple market areas while respecting economic and network constraints.

## Quick Start

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.market_clearing import MarketClearingModule

dataset = AtlasDataset.from_directory("path/to/dataset")
result = ModuleRun(
    module=MarketClearingModule(),
    dataset=dataset,
    parameters="path/to/parameters.yml",
).run()
```

See [Running Modules](../running-modules.md) for execution details.

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
- [Parameters](user-guide/parameters.md): Module-specific parameters
- [Results](user-guide/results.md): Accessing outputs

### Common Documentation
- [Module Pattern](../module-pattern.md): ATLAS module architecture
- [Common Parameters](../common-parameters.md): Shared configuration options
- [Running Modules](../running-modules.md): General execution guide

### Developer Reference
- [Architecture](developer/architecture.md): Module design and structure
