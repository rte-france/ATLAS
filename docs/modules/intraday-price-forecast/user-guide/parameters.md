# Parameters

## Overview

The Intraday Price Forecast module is configured through `IntradayPriceForecastParameters`. Parameters can be provided as a dictionary or loaded from a JSON/YAML file.

## Price Caps

* **`intraday_negative_price_cap`** (`int`, default: `-500`): Lower price cap of the Intraday market.

    * Must be less than or equal to 0
    * Expressed in €/MWh
    * Current market value: -500 €/MWh (as of 2024)

* **`intraday_positive_price_cap`** (`int`, default: `4000`): Upper price cap of the Intraday market.

    * Must be greater than or equal to 0
    * Expressed in €/MWh
    * Current market value: 4000 €/MWh (as of 2024)

---

## Execution Dates

* **`execution_date_day_ahead`** (`DateTime`, required): Reference date from Day-Ahead market.

    * Used to retrieve day-ahead consumption forecasts
    * Must be a valid datetime with timezone information

* **`execution_date_scenarios`** (`DateTime`, required): Reference date for the scenarios from price forecast matrix.

    * Used to retrieve high/low price and consumption scenarios
    * Must be a valid datetime with timezone information

---

## Example Configuration

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

## Required Input Data

The module requires the following data in the input dataset:

### Market Areas

Each market area must have:

- `price_forecast_high`: High price scenario (ForecastingMatrix)
- `price_forecast_low`: Low price scenario (ForecastingMatrix)
- `da_price`: Day-ahead price (AbstractTimeseries)
- `id_price`: Intraday price history (optional, dict of Timeseries)

### Loads

Each load must have:

- `maximum_power_forecast`: Power forecasts for different execution dates (ForecastingMatrix)
- `power_forecast_high`: High consumption scenario (ForecastingMatrix)
- `power_forecast_low`: Low consumption scenario (ForecastingMatrix)
- `load_type`: Must be `LoadType.BASE_LOAD` to be included in calculations

### Solar Units

Each solar unit must have:

- `maximum_power_forecast`: Power forecasts for different execution dates (ForecastingMatrix)

### Wind Units

Each wind unit must have:

- `maximum_power_forecast`: Power forecasts for different execution dates (ForecastingMatrix)

---

## Next Steps

- [Results](results.md): Understanding outputs
