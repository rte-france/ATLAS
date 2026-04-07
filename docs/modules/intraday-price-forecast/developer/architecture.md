# Module Architecture

## Overview

The Intraday Price Forecast module follows ATLAS's `AbstractModule` pattern. See [Module Pattern](../../../concepts/module-pattern.md) for details on the standard module architecture.

This document describes the module-specific architecture and components.

## Module Structure

```
intraday_price_forecast/
├── __init__.py                           # Module exports
├── module.py                             # Core module implementation
├── parameters.py                         # Configuration parameters
├── input_dataset.py                      # Input data aggregation
├── output_dataset.py                     # Output data aggregation
├── orchestrator.py                       # Main computation logic
└── models/                               # Intraday-specific models
    ├── __init__.py
    ├── portfolio.py                      # Portfolio model
    ├── market_area.py                    # Market area model
    ├── load.py                           # Load model
    ├── solar.py                          # Solar model
    └── wind.py                           # Wind model
```

## Core Classes

### IntradayPriceForecastModule

Implements `AbstractModule` with methods:

- `get_parameters_class()`: Returns `IntradayPriceForecastParameters`
- `import_data()`: Creates `IntradayPriceForecastInputDataset`
- `validate_data()`: Returns `True` (validation delegated to Pydantic models)
- `execute()`: Runs orchestrator and returns `IntradayPriceForecastOutputDataset`
- `validates_results()`: Checks all market areas have price forecasts
- `export_results()`: Returns without action (data updated in place)

### IntradayPriceForecastParameters

Pydantic model inheriting from `AbstractModuleParameters`. Defines configuration parameters:

- `temporal`: Time configuration (inherited)
- `output`: Output configuration (inherited)
- `intraday_negative_price_cap`: Lower price limit
- `intraday_positive_price_cap`: Upper price limit
- `execution_date_day_ahead`: Day-ahead reference date
- `execution_date_scenarios`: Scenarios reference date
- `penultimate_date`: Cached property for `end_date - timestep`

See [Parameters](../user-guide/input-data.md) for details.

### IntradayPriceForecastInputDataset

Converts business models to intraday-specific models:

- Creates `MarketAreaIDPF` instances from input market areas
- Creates `LoadIDPF`, `SolarIDPF`, `WindIDPF` instances with references to market areas
- Builds a market area mapping for portfolio-to-market-area relationships

### IntradayPriceForecastOutputDataset

Inherits from `AbstractModuleOutput`. Contains:

- `market_area`: List of market areas with updated price forecasts
- `build_change_sets()`: Creates `UpdateObject` change sets for each market area's `id_price_forecast`

### IntradayPriceForecastOrchestrator

Contains the main computation logic. Key methods:

#### Public Methods

- `execute()`: Main entry point that processes all market areas

#### Private Methods

- `_filter_assets_by_market_area()`: Filters loads, solar, and wind by market area
- `_create_empty_timeseries()`: Creates zero-initialized timeseries
- `_compute_price_sensitivity_ratio()`: Calculates `(price_high - price_low) / (consumption_low - consumption_high)`
- `_compute_consumption_delta()`: Calculates intraday vs day-ahead residual consumption difference
- `_get_baseline_price()`: Selects latest intraday or day-ahead price
- `_apply_non_negativity_constraint()`: Ensures prices ≥ 0
- `_apply_price_caps()`: Scales prices if they exceed caps
- `_apply_single_price_cap()`: Applies a single cap (upper or lower)
- `_save_price_forecast()`: Saves results to market area's forecasting matrix

## Models

### MarketAreaIDPF

Extends `MarketArea` with intraday-specific attributes:

- `price_forecast_low`: Low price scenario (ForecastingMatrix)
- `price_forecast_high`: High price scenario (ForecastingMatrix)
- `da_price`: Day-ahead price (AbstractTimeseries)

### LoadIDPF

Extends `Load` with intraday-specific attributes:

- `power_forecast_low`: Low consumption scenario (ForecastingMatrix)
- `power_forecast_high`: High consumption scenario (ForecastingMatrix)

### SolarIDPF / WindIDPF

Extend `Solar` and `Wind` base classes (no additional attributes currently).

### PortfolioIDPF

Extends `Portfolio` to maintain market area references in the intraday context.

## Data Flow

```
run(raw_data, raw_params)
  ↓
import_parameters() → IntradayPriceForecastParameters
  ↓
import_data() → IntradayPriceForecastInputDataset
  ↓
validate_data() → True
  ↓
execute()
  ├→ IntradayPriceForecastOrchestrator.execute()
  │   ├→ For each market area:
  │   │   ├→ _filter_assets_by_market_area()
  │   │   ├→ _compute_price_sensitivity_ratio()
  │   │   ├→ _compute_consumption_delta()
  │   │   ├→ _get_baseline_price()
  │   │   ├→ Apply formula: baseline + ratio × delta
  │   │   ├→ _apply_non_negativity_constraint()
  │   │   ├→ _apply_price_caps()
  │   │   └→ _save_price_forecast()
  │   └→ Return IntradayPriceForecastOutputDataset
  ↓
validates_results() → Check all market areas have forecasts
  ↓
export_results() → Update market areas in place via change sets
```

## Algorithm Details

### Price Sensitivity Ratio

For each timestep:

```
price_diff = price_forecast_high[t] - price_forecast_low[t]
consumption_diff = power_forecast_low[t] - power_forecast_high[t]

if consumption_diff ≠ 0:
    ratio[t] = price_diff / consumption_diff
else:
    ratio[t] = 0
```

### Consumption Delta

```
residual_consumption[t] = load[t] - solar[t] - wind[t]

delta[t] = residual_consumption_intraday[t] - residual_consumption_day_ahead[t]
```

### Price Forecast

```
forecast[t] = baseline_price[t] + ratio[t] × delta[t]

# Apply constraints
forecast[t] = max(0, forecast[t])  # Non-negativity

# Apply caps (proportional scaling if exceeded)
if max(forecast) > positive_cap:
    forecast *= positive_cap / max(forecast)

if min(forecast) < negative_cap:
    forecast *= negative_cap / min(forecast)
```

## Module-Specific Design Patterns

For common ATLAS patterns (module lifecycle, Pydantic models), see [Module Pattern](../../../concepts/module-pattern.md).

**Sensitivity-Based Forecasting**: Uses scenario analysis (high/low) to estimate price-consumption relationships

**Residual Consumption**: Computes net load by subtracting renewable generation from consumption

**Proportional Scaling**: When price caps are exceeded, all values are scaled to bring the extreme value to the cap

**Baseline Selection**: Prioritizes latest intraday price over day-ahead price when available
