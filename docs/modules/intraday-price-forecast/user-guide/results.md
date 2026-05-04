# Results

## Overview

Results are stored in market area objects after forecasting completes.

## Accessing Results

```python
from atlas import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.modules.intraday_price_forecast import IntradayPriceForecastModule

dataset = AtlasDataset.from_directory("path/to/dataset")
result = ModuleRun(
    module=IntradayPriceForecastModule(),
    dataset=dataset,
    parameters="parameters.yml",
).run()

# Intraday price forecasts per market area
for market_area in result.market_areas:
    forecast = market_area.id_price_forecast.get_forecast(
        execution_date, start_date, end_date
    )
    print(market_area.name, forecast.dataframe)
```

## Key Outputs

- **Intraday price forecasts**: Price forecasts per market area and execution date (stored in `market_area.id_price_forecast`)

## Price Forecast Format

The forecast is stored as a `ForecastingMatrix` on each `MarketArea`. Each column corresponds to an execution date, each row to a timestep.

## Troubleshooting

**No forecast generated**: Check that the market area has `price_forecast_high`, `price_forecast_low`, and `da_price` data at the configured `execution_date_scenarios` and `execution_date_day_ahead`.

**Forecast capped at price limits**: The module applies proportional scaling when forecasts exceed `intraday_positive_price_cap` or `intraday_negative_price_cap`. This is expected behaviour.
