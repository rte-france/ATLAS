# Portfolio Optimisation Module

## Overview

Optimizes energy portfolios including thermal, hydro, storage, solar, wind, and load assets for different market conditions.

## Quick Start

```python
from atlas import AtlasDataset, PortfolioOptimisationModule

module = PortfolioOptimisationModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
module.run(input_data, "path/to/parameters.yml")
```

See [Running Modules](../../concepts/running-modules.md) for execution details.

## Key Features

- **Portfolio-level optimization**: Optimize entire portfolios with imbalance penalties
- **Individual unit optimization**: Optimize each unit independently
- **Multi-asset support**: Thermal, hydro, storage, solar, wind, and load
- **Parallel execution**: Multiprocessing support for large portfolios
- **Flexible constraints**: Manual activation rules and equipment exclusions

## Documentation

### User Guide
- [Overview](user-guide/overview.md): Module-specific introduction
- [Parameters](user-guide/input-data.md): Module-specific parameters
- [Running](user-guide/running.md): Execution modes and options
- [Results](user-guide/results.md): Accessing outputs
- [Examples](user-guide/examples.md): Usage examples

### Common Documentation
- [Module Pattern](../../concepts/module-pattern.md): ATLAS module architecture
- [Common Parameters](../../concepts/common-parameters.md): Shared configuration options
- [Running Modules](../../concepts/running-modules.md): General execution guide

### Developer Reference
- [Architecture](developer/architecture.md): Module design and structure
