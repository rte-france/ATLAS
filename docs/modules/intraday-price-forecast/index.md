# Intraday Price Forecast Module

## Overview

Computes intraday price forecasts based on consumption changes between day-ahead and intraday markets, weighted by price sensitivity ratios derived from scenario analysis.

## Quick Start

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.intraday_price_forecast import IntradayPriceForecastModule

dataset = AtlasDataset.from_directory("path/to/dataset")
result = ModuleRun(
    module=IntradayPriceForecastModule(),
    dataset=dataset,
    parameters="path/to/parameters.yml",
).run()
```

See [Running Modules](../running-modules.md) for execution details.

## Key Outputs

- **Intraday price forecasts**: Per market area and execution date
- **Updated forecasting matrices**: Added to market area `id_price_forecast` attribute

## Key Features

- **Scenario-based sensitivity**: Uses high/low scenarios to estimate price-consumption relationships
- **Multi-asset support**: Considers loads, solar, and wind generation
- **Price cap enforcement**: Ensures forecasts stay within market limits
- **Baseline selection**: Prioritizes latest intraday price over day-ahead when available

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
