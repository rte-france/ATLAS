# Results

## Overview

Results are stored in business model objects:

- **Equipment**:
    * `power` attribute (ForecastingMatrix)
    * `stored_energy` attribute (ForecastingMatrix), only for Storage and Hydraulic Equipments
- **Portfolio**: `imbalance` attribute (ForecastingMatrix)

## Accessing Results

```python
# Equipment power forecast
forecast = equipment.power.get_forecast(execution_date, start_date, end_date)
df = forecast.dataframe

# Portfolio imbalance
imbalance = portfolio.imbalance.get_forecast(execution_date, start_date, end_date)
```

## Conventions for Power matrix, by Equipment Type

- **Thermal/Hydro**: Generation (MW)
- **Storage**: Charge (negative) / Discharge (positive) (MW). These values are seen from the power system perspective, charge / discharge efficiencies are taken into account later on, when updating stored energy levels.
- **Wind/Solar**: Generation output (MW). Curtailed power (MW) can be deduced by the difference between 'maximum_power_forecast' ForecastingMatrix and the Power output from the Portfolio Optimization
- **Load**: Consumption (MW), noted as a negative Power output in ATLAS

## Imbalance

This module allows the market actors (the Portfolios) to do arbitrage between their market commitments and their generation costs. Technical constraints on units can also prevent them from being able to follow their market commitments.
Consequently, actors can be imbalanced after the execution of the module. This is tracked by the `imbalance` attribute, computed as follows:

```
imbalance = large_imbalance_down + small_imbalance_down
          - large_imbalance_up - small_imbalance_up
```

The convention is then the following: positive for over-generation, negative for under-generation.

## Troubleshooting

**No power update**: Check if `export_result=True`, check if the parameters (notably the dates parameters or the market type) are correct. Note that unsuccesful optimizations, or excluding certain equipments / market areas from optimizations, should still lead to power updates. Indeed, a specific backup is applied in those situations, the `manual_activation` process.

**Zero generation**: Check startup/min generation constraints, fuel costs vs prices, min up/down times
