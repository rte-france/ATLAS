# Results

## Overview

Results are stored in business model objects:
- **Equipment**: `power` attribute (ForecastingMatrix)
- **Portfolio**: `imbalance` attribute (ForecastingMatrix)

## Accessing Results

```python
# Equipment power forecast
forecast = equipment.power.get_forecast(execution_date, start_date, end_date)
df = forecast.dataframe

# Portfolio imbalance
imbalance = portfolio.imbalance.get_forecast(execution_date, start_date, end_date)
```

## Power Values by Equipment Type

- **Thermal/Hydro**: Generation (MW)
- **Storage**: Charge (negative) / Discharge (positive) (MW)
- **Wind/Solar**: Curtailed power (MW)
- **Load**: Consumption (MW)

## Imbalance

```
imbalance = large_imbalance_down + small_imbalance_down
          - large_imbalance_up - small_imbalance_up
```

Positive = over-generation, Negative = under-generation

## Troubleshooting

**No power update**: Check `export_result=True`, verify optimization succeeded, check if equipment was excluded

**Unexpected values**: Verify input data, check solver status, review parameters, enable `debug=True`

**Zero generation**: Check startup/min generation constraints, fuel costs vs prices, min up/down times
