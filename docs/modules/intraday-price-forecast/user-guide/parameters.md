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

- [Input Objects](input-objects.md): Required input data and attributes
- [Results](results.md): Understanding outputs
