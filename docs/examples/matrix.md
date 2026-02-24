# Matrix Usage Examples

Atlas provides matrix classes for managing collections of time series data: `ScenarioMatrix` for scenario-based data and `ForecastingMatrix` for time-indexed forecasts.

## ScenarioMatrix

The `ScenarioMatrix` stores multiple time series as columns, where each column represents a different scenario or data series.

### Creating a ScenarioMatrix

#### From File

```python
from atlas.math.matrix import ScenarioMatrix

# Load from file (CSV or Parquet)
matrix = ScenarioMatrix.from_file("data/scenarios.parquet", timezone="UTC")
```

#### From DataFrame

```python
import polars as pl

# Create from Polars DataFrame with multiple scenarios
df = pl.DataFrame({
    "time": pl.datetime_range(start="2024-01-01", end="2024-01-02", interval="1h"),
    "scenario_1": [10.0, 12.0, 15.0, ...],
    "scenario_2": [11.0, 13.0, 14.0, ...],
    "scenario_3": [9.0, 11.0, 16.0, ...]
})

matrix = ScenarioMatrix(df, timezone="UTC")
```

#### Building from Timeseries

```python
from atlas.math.timeseries import Timeseries

# Create empty matrix
matrix = ScenarioMatrix(timezone="UTC")

# Add timeseries one by one
ts1 = Timeseries.from_values(
    start_date="2024-01-01 00:00:00",
    frequency="1h",
    values=[10.5, 12.3, 15.7]
)

ts2 = Timeseries.from_values(
    start_date="2024-01-01 00:00:00",
    frequency="1h",
    values=[11.2, 13.1, 14.8]
)

matrix.add(timeseries=ts1, index="scenario_1")
matrix.add(timeseries=ts2, index="scenario_2")
```

### Accessing Data

```python
# Get list of scenario names
scenarios = matrix.indexes  # or matrix.index

# Check if scenario exists
if "scenario_1" in matrix:
    print("Scenario exists")

# Get specific scenario as Timeseries
ts = matrix["scenario_1"]
# or
ts = matrix.select("scenario_1")

# Get number of scenarios
num_scenarios = len(matrix)

# Access as DataFrame
df = matrix.dataframe  # or matrix.get_matrix()

# Get shape
shape = matrix.shape  # (rows, columns)

# Get metadata
metadata = matrix.metadata  # or matrix.describe()
```

### Modifying Scenarios

```python
# Add new scenario
new_ts = Timeseries.from_values(
    start_date="2024-01-01 00:00:00",
    frequency="1h",
    values=[8.0, 9.5, 11.0]
)
matrix.add(timeseries=new_ts, index="scenario_3")

# Replace existing scenario
matrix.replace(index="scenario_1", timeseries=new_ts)

# Delete scenario
matrix.delete("scenario_2")
```

### Resampling

```python
# Change frequency for all scenarios
matrix_hourly = matrix.set_frequency("1h")

# This automatically upsamples or downsamples based on current frequency
matrix_daily = matrix.set_frequency("1d")
```

### Exporting Data

```python
# Export to file
matrix.to_file("output/scenarios.csv", file_format="csv")
matrix.to_file("output/scenarios.parquet", file_format="parquet")
matrix.to_file("output/scenarios.pickle", file_format="pickle")

# Export with attribute column
matrix.to_file_with_attribute(
    path="output/scenarios.parquet",
    attribute="my_equipment",
    file_format="parquet",
    concatenate=True
)
```

### Visualization

```python
# Create interactive plot with scenario selector
fig = matrix.plot(
    title="Scenario Analysis",
    height=600,
    width=1000,
    line_shape="linear",
    template="plotly_white"
)

# Display or save
fig.show()
# fig.write_html("output/scenarios.html")
```

## ForecastingMatrix

The `ForecastingMatrix` is a specialized matrix where each column represents a forecast generated at a specific datetime. Column names are datetime strings.

### Creating a ForecastingMatrix

#### From File

```python
from atlas.math.forecasting_matrix import ForecastingMatrix

# Load from file
forecast_matrix = ForecastingMatrix.from_file(
    "data/forecasts.parquet",
    timezone="UTC",
    date_format="YYYY-MM-DD HH:mm:ss"
)
```

#### Building from Timeseries

```python
from atlas.math.timeseries import Timeseries
from atlas.math.forecasting_matrix import ForecastingMatrix

# Create empty forecasting matrix
forecast_matrix = ForecastingMatrix(
    timezone="UTC",
    date_format="YYYY-MM-DD HH:mm:ss"
)

# Add forecasts with datetime indexes
forecast_0h = Timeseries.from_values(
    start_date="2024-01-01 00:00:00",
    frequency="1h",
    values=[10.0, 11.0, 12.0, 13.0]
)

forecast_6h = Timeseries.from_values(
    start_date="2024-01-01 06:00:00",
    frequency="1h",
    values=[11.5, 12.5, 13.5, 14.5]
)

# Add with datetime index
forecast_matrix.add(timeseries=forecast_0h, index="2024-01-01 00:00:00")
forecast_matrix.add(timeseries=forecast_6h, index="2024-01-01 06:00:00")
```

### Accessing Forecasts

```python
from datetime import datetime

# Check if forecast exists
if "2024-01-01 00:00:00" in forecast_matrix:
    print("Forecast exists")

# Get specific forecast as Timeseries
ts = forecast_matrix["2024-01-01 00:00:00"]
# or
ts = forecast_matrix.select("2024-01-01 00:00:00")

# Get list of forecast dates
forecast_dates = forecast_matrix.indexes

# Access using datetime objects
ts = forecast_matrix[datetime(2024, 1, 1, 0, 0, 0)]
```

### Modifying Forecasts

```python
# Add new forecast
new_forecast = Timeseries.from_values(
    start_date="2024-01-01 12:00:00",
    frequency="1h",
    values=[12.0, 13.0, 14.0]
)
forecast_matrix.add(timeseries=new_forecast, index="2024-01-01 12:00:00")

# Replace existing forecast
forecast_matrix.replace(index="2024-01-01 00:00:00", timeseries=new_forecast)

# Delete forecast
forecast_matrix.delete("2024-01-01 06:00:00")
```

### Getting Best Forecast

The `get_forecast()` method retrieves the most up-to-date forecast for each timestamp, prioritizing newer forecasts and filling gaps from older ones:

```python
# Get best forecast for a time window
best_forecast = forecast_matrix.get_forecast(
    execution_date="2024-01-01 12:00:00",  # Only use forecasts made before this
    start_date="2024-01-01 00:00:00",       # Start of forecast window
    end_date="2024-01-02 00:00:00",         # End of forecast window
    timestep="1h",                           # Target frequency
    default_value=0.0                        # Fill missing values with 0
)

# The result is a Timeseries with the best available forecast for each timestamp
```

**How it works:**

- Only forecasts made on or before `execution_date` are considered
- For each timestamp, the newest available forecast is used
- Gaps are filled with older forecasts
- Missing values can be filled with `default_value`

### Date Format Management

```python
# Get current date format
date_format = forecast_matrix.date_format

# Change date format (re-formats column names)
forecast_matrix.set_date_format("YYYY-MM-DD HH:mm")
```

### Resampling

```python
# Change frequency for all forecasts
forecast_matrix.set_frequency("30m", inplace=True)
```

## Lazy Matrices

For large datasets, use lazy evaluation with `LazyScenarioMatrix` and `LazyForecastingMatrix`:

### LazyScenarioMatrix

```python
from atlas.math.lazy_matrix import LazyScenarioMatrix

# Load lazily from file
lazy_matrix = LazyScenarioMatrix.from_file("data/large_scenarios.parquet")

# Operations are deferred until collect() is called
lazy_matrix.add(timeseries=ts, index="scenario_new")

# Collect to get eager ScenarioMatrix
matrix = lazy_matrix.collect()
```

### LazyForecastingMatrix

```python
from atlas.math.forecasting_matrix import LazyForecastingMatrix

# Load lazily
lazy_forecast = LazyForecastingMatrix.from_file(
    "data/large_forecasts.parquet",
    date_format="YYYY-MM-DD HH:mm:ss"
)

# Get forecast (automatically collects)
best_forecast = lazy_forecast.get_forecast(
    execution_date="2024-01-01 12:00:00",
    start_date="2024-01-01 00:00:00",
    end_date="2024-01-02 00:00:00"
)
```

## Common Properties

All matrix types share these properties:

```python
# Access underlying data
df = matrix.dataframe           # Polars DataFrame
lazy_df = matrix.to_lazy()      # LazyFrame for deferred computation

# Shape and indexes
shape = matrix.shape             # (rows, columns)
indexes = matrix.indexes         # List of column names (scenarios/forecasts)
num_series = len(matrix)        # Number of series in matrix

# Metadata
metadata = matrix.metadata      # Dictionary with matrix info
timezone = matrix.timezone      # Timezone string
```

For more information, see the API references:

- [ScenarioMatrix API](../api/math/scenario_matrix.md)
- [ForecastingMatrix API](../api/math/forecasting_matrix.md)
