# Portfolio Optimisation Module

## Overview

Optimizes energy portfolios including thermal, hydro, storage, solar, wind, and load assets for different market conditions.

## Quick Start

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.portfolio_optimisation import PortfolioOptimisationModule

dataset = AtlasDataset.from_directory("path/to/dataset")
result = ModuleRun(
    module=PortfolioOptimisationModule(),
    dataset=dataset,
    parameters="path/to/parameters.yml",
).run()
```

See [Running Modules](../running-modules.md) for execution details.

## Key Features

- **Portfolio-level optimization**: Optimize entire portfolios with imbalance penalties
- **Individual unit optimization**: Optimize each unit independently
- **Multi-asset support**: Thermal, hydro, storage, solar, wind, and load
- **Parallel execution**: Multiprocessing support for large portfolios
- **Flexible constraints**: Manual activation rules and equipment exclusions

## Documentation

### User Guide
- [Overview](user-guide/overview.md): Module-specific introduction
- [Parameters](user-guide/parameters.md): Module-specific parameters
- [Results](user-guide/results.md): Accessing outputs
- [Examples](user-guide/examples.md): Usage examples

### Common Documentation
- [Module Pattern](../module-pattern.md): ATLAS module architecture
- [Common Parameters](../common-parameters.md): Shared configuration options
- [Running Modules](../running-modules.md): General execution guide

### Developer Reference
- [Architecture](developer/architecture.md): Module design and structure
