# Market Clearing Module

## Overview

Determines market equilibrium by matching supply and demand across multiple market areas while respecting economic and network constraints. Can be used for different types of product (wholesale energy markets, reserve procurement or reserve activation).

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
- **Network constraints**: Respects transmission capacity limits, in both ATC and Flow-Based modes
- **Economic optimization**: Maximizes social welfare, while respecting constraints on market orders and their coupling links
- **Sequential process**: Similarly to actual Market Clearing algorithms (Euphemia on the day-ahead market for instance), the module is divided in several steps (welfare maximization, exchange fixing, price determination, marginal volume fixing).

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
