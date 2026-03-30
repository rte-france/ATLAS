# Intraday Price Forecast Module

## Overview

Computes intraday price forecasts based on consumption changes between day-ahead and intraday markets, weighted by price sensitivity ratios derived from scenario analysis.

## Quick Start

```python
from atlas import AtlasDataset, IntradayPriceForecastModule

module = IntradayPriceForecastModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
module.run(input_data, "path/to/parameters.yml")
```

See [Running Modules](../../concepts/running-modules.md) for execution details.

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
- [Parameters](user-guide/input-data.md): Module-specific parameters
- [Running](user-guide/running.md): Execution details

### Common Documentation
- [Module Pattern](../../concepts/module-pattern.md): ATLAS module architecture
- [Common Parameters](../../concepts/common-parameters.md): Shared configuration options
- [Running Modules](../../concepts/running-modules.md): General execution guide

### Developer Reference
- [Architecture](developer/architecture.md): Module design and structure
