# Input Objects

This page describes the input data required by the Intraday Price Forecast module per object type.

---

## Market Areas

| Field | Type | Description |
|---|---|---|
| `price_forecast_low` | `ForecastingMatrix` | Low price scenario. Combined with `price_forecast_high` to compute price sensitivity ratios. |
| `price_forecast_high` | `ForecastingMatrix` | High price scenario. Combined with `price_forecast_low` to compute price sensitivity ratios. |
| `da_price` | `AbstractTimeseries` | Day-ahead prices from market clearing. Serves as the baseline before applying intraday adjustments. |

---

## Load Units

Only units with `load_type = BASE_LOAD` are included in consumption delta calculations.

| Field | Type | Description |
|---|---|---|
| `load_type` | `LoadType` | Must be `BASE_LOAD` for the unit to be included. |
| `maximum_power_forecast` | `ForecastingMatrix` | Intraday power forecasts indexed by execution date. Used to compute the consumption delta relative to the day-ahead forecast. |
| `power_forecast_high` | `AbstractTimeseries` | High consumption scenario used to compute price sensitivity. |
| `power_forecast_low` | `AbstractTimeseries` | Low consumption scenario used to compute price sensitivity. |

---

## Solar Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | Intraday solar generation forecasts indexed by execution date. |

---

## Wind Units

| Field | Type | Description |
|---|---|---|
| `maximum_power_forecast` | `ForecastingMatrix` | Intraday wind generation forecasts indexed by execution date. |

---

## Next Steps

- [Parameters](parameters.md): Module-specific configuration options
- [Results](results.md): Accessing outputs
