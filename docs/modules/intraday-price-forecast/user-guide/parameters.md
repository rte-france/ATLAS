# Parameters

The Intraday Price Forecast module is configured through `IntradayPriceForecastParameters`. Parameters can be provided as a dictionary or loaded from a JSON/YAML file.

---

## Price Caps

| Parameter | Type | Default | Description |
|---|---|---|---|
| `intraday_negative_price_cap` | `int` | `-500` €/MWh | Lower price cap of the Intraday market. Must be ≤ 0. Current market value as of 2024. |
| `intraday_positive_price_cap` | `int` | `4 000` €/MWh | Upper price cap of the Intraday market. Must be ≥ 0. Current market value as of 2024. |

## Execution Dates

| Parameter | Type | Required | Description |
|---|---|---|---|
| `execution_date_day_ahead` | `DateTime` | Yes | Reference date from the Day-Ahead market. Used to retrieve day-ahead consumption forecasts. |
| `execution_date_scenarios` | `DateTime` | Yes | Reference date for scenario retrieval from the price forecast matrix (high/low prices and consumption). |

---

## Required Input Data

### Market Areas

| Field | Type | Description |
|---|---|---|
| `price_forecast_high` | `ForecastingMatrix` | High price scenario. |
| `price_forecast_low` | `ForecastingMatrix` | Low price scenario. |
| `da_price` | `AbstractTimeseries` | Day-ahead price. |
| `id_price` | `dict[str, Timeseries]` | Intraday price history (optional). |

### Load Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | Power forecasts indexed by execution date. |
| `power_forecast_high` | `ForecastingMatrix` | High consumption scenario. |
| `power_forecast_low` | `ForecastingMatrix` | Low consumption scenario. |
| `load_type` | `LoadType` | Must be `LoadType.BASE_LOAD` to be included in calculations. |

### Solar & Wind Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | Power forecasts indexed by execution date. |

---

## Example Configuration

```yaml
temporal:
  start_date: "2024-01-01 00:00:00"
  end_date: "2024-01-02 00:00:00"
  execution_date: "2024-01-01 12:00:00"
  timestep: "PT1H"
output:
  export_result: true
  export_output_dataset: true
intraday_negative_price_cap: -500
intraday_positive_price_cap: 4000
execution_date_day_ahead: "2024-01-01 06:00:00"
execution_date_scenarios: "2024-01-01 00:00:00"
```

## Next Steps

- [Results](results.md): Understanding outputs
