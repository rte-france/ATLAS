# Running the Module

## Basic Usage

See [Running Modules](../../../concepts/running-modules.md) for the standard ATLAS module execution pattern and parameter formats.

For common parameters (dates, timestep, etc.), see [Common Parameters](../../../concepts/common-parameters.md).

## Module-Specific Parameters

This module adds the following parameters beyond the common ones:

### Price Caps

**`intraday_negative_price_cap`** (integer): Lower price limit
- Default: `-500` (€/MWh)
- Must be ≤ 0

**`intraday_positive_price_cap`** (integer): Upper price limit
- Default: `4000` (€/MWh)
- Must be ≥ 0

### Execution Dates

**`execution_date_day_ahead`** (datetime): Reference date for day-ahead market data
- Required
- Used to retrieve day-ahead consumption forecasts

**`execution_date_scenarios`** (datetime): Reference date for price/consumption scenarios
- Required
- Used to retrieve high/low scenario data

## Example Configuration

### Python API

```python
from atlas import AtlasDataset, IntradayPriceForecastModule

params = {
    # Common parameters
    "start_date": "2024-01-01T00:00:00",
    "end_date": "2024-01-02T00:00:00",
    "execution_date": "2024-01-01T12:00:00",
    "timestep": "PT1H",
    "export_result": True,

    # Module-specific parameters
    "intraday_negative_price_cap": -500,
    "intraday_positive_price_cap": 4000,
    "execution_date_day_ahead": "2024-01-01T06:00:00",
    "execution_date_scenarios": "2024-01-01T00:00:00"
}

module = IntradayPriceForecastModule()
input_data = AtlasDataset.from_directory("path/to/dataset")
output = module.run(input_data, params)
```

### YAML Configuration

```yaml
temporal:
  start_date: "2024-01-01 00:00:00"
  end_date: "2024-01-02 00:00:00"
  execution_date: "2024-01-01 12:00:00"
  timestep: "1h"

output:
  export_result: True
  export_output_dataset: True

intraday_negative_price_cap: -500
intraday_positive_price_cap: 4000
execution_date_day_ahead: "2024-01-01 06:00:00"
execution_date_scenarios: "2024-01-01 00:00:00"
```

### CLI Usage

```bash
atlas run parameters.yaml \
  --module IntradayPriceForecast \
  --dataset ./data/input/
```

## Output

The module updates the input dataset with:

- **`id_price_forecast`**: Added to each market area's forecasting matrix
  - Contains intraday price forecasts for the execution date
  - Accessible via `market_area.id_price_forecast`

## Validation

The module validates results by checking:

1. All market areas have `id_price_forecast` populated
2. The execution date exists in each market area's forecast matrix

If validation fails, the module logs errors and returns `False` from `validates_results()`.

## Common Issues

### Missing Scenario Data

**Error**: Price sensitivity ratio is zero for all timesteps

**Cause**: High/low price or consumption scenarios not available at `execution_date_scenarios`

**Solution**: Ensure `price_forecast_high`, `price_forecast_low`, `power_forecast_high`, and `power_forecast_low` contain data for the specified execution date

### Price Cap Violations

**Warning**: "ID price forecasts upper/lower capped in area [name]"

**Meaning**: Forecasted prices exceeded caps and were scaled proportionally

**Action**: This is expected behavior; review if scaling is excessive

## Next Steps

See [Parameters](input-data.md) for the complete list of module-specific parameters.
