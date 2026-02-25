# Timeseries Usage Example

The `Timeseries` class provides a flexible and efficient interface for handling time series data using a Polars backend.

## Creating a Timeseries

### From File

```python
from atlas.math.timeseries import Timeseries

# Load from file (CSV or Parquet)
ts = Timeseries.from_file("data/timeseries.parquet", timezone="UTC")
```

### From Values

```python
# Create from start date, frequency, and values
ts = Timeseries.from_values(
    start_date="2024-01-01 00:00:00",
    frequency="1h",
    values=[10.5, 12.3, 15.7, 14.2],
    timezone="UTC"
)
```

### From Index

```python
# Create with date range and default value
ts = Timeseries.from_index(
    start_date="2024-01-01 00:00:00",
    end_date="2024-01-02 00:00:00",
    frequency="1h",
    default_value=0.0,
    timezone="UTC"
)
```

### From DataFrame

```python
import polars as pl

# Create from Polars DataFrame
df = pl.DataFrame({
    "time": pl.datetime_range(start="2024-01-01", end="2024-01-02", interval="1h"),
    "value": [1.0, 2.0, 3.0, ...]
})

ts = Timeseries.from_dataframe(df, timezone="UTC")
```

## Accessing Data

```python
# Get values and timestamps
values = ts.values  # List of values
timestamps = ts.index  # List of datetime objects

# Get value at specific time
value = ts.get_value("2024-01-01 12:00:00")

# Check if timestamp exists
if "2024-01-01 12:00:00" in ts:
    print("Timestamp exists")

# Get metadata
metadata = ts.metadata  # or ts.describe()

# Access as DataFrame
df = ts.dataframe  # Polars DataFrame
df_pandas = ts.to_frame(engine="pandas")  # Pandas DataFrame
```

## Modifying Values

### Set Individual Values

```python
# Set value at specific time
ts.set_value(time="2024-01-01 12:00:00", value=25.5)

# Add to existing value
ts.sum_value_at(time="2024-01-01 12:00:00", value=5.0)

# Multiply existing value
ts.mul_value_at(time="2024-01-01 12:00:00", value=2.0)
```

### Set Multiple Values

```python
# Update multiple values from another timeseries
other_ts = Timeseries.from_values(
    start_date="2024-01-01 00:00:00",
    frequency="1h",
    values=[20.0, 21.0, 22.0]
)

ts.set_values(other_ts)
```

### Add Indexes

```python
# Add new timestamp with value
ts.add_index(time="2024-01-03 00:00:00", value=30.0)

# Add multiple indexes from another timeseries
ts.add_indexes(other_ts)
```

## Arithmetic Operations

```python
# Scalar operations
ts_doubled = ts * 2
ts_plus_10 = ts + 10
ts_minus_5 = ts - 5
ts_divided = ts / 2

# Timeseries operations
ts_sum = ts + other_ts
ts_diff = ts - other_ts
ts_product = ts * other_ts
ts_ratio = ts / other_ts
```

## Resampling and Aggregation

### Change Frequency

```python
# Upsample to higher frequency
ts_15min = ts.upsample(frequency="15m", interpolation_method="linear")

# Downsample with aggregation
ts_daily = ts.groupby(frequency="1d", agg="mean")

# Automatically resample (up or down)
ts_hourly = ts.set_frequency("1h")
```

### Group By with Aggregations

```python
# Group by day and aggregate
ts_daily_sum = ts.groupby(frequency="1d", agg="sum")
ts_daily_max = ts.groupby(frequency="1d", agg="max")
ts_daily_min = ts.groupby(frequency="1d", agg="min")
```

## Timezone Handling

```python
# Change timezone
ts.set_timezone("Europe/Paris")

# Create with specific timezone
ts = Timeseries.from_index(
    start_date="2024-01-01 00:00:00",
    end_date="2024-01-02 00:00:00",
    frequency="1h",
    timezone="America/New_York"
)
```

## Exporting Data

```python
# Export to file
ts.to_file("output/timeseries.csv", file_format="csv")
ts.to_file("output/timeseries.parquet", file_format="parquet")
ts.to_file("output/timeseries.pickle", file_format="pickle")

# Export with attribute column
ts.to_file_with_attribute(
    path="output/timeseries.parquet",
    attribute="my_equipment",
    file_format="parquet",
    concatenate=True  # Append to existing file
)
```

## Statistical Methods

```python
# Get statistics
max_value = ts.max()
min_value = ts.min()
total = ts.sum()

# Get date range
first = ts.first_date()
last = ts.last_date()

# Get shape and length
shape = ts.shape  # (rows, columns)
length = len(ts)  # number of rows
```

## Interpolation

```python
# Fill missing values with interpolation
ts_interpolated = ts.interpolate(interpolation_method="linear")

# Fill with forward fill
ts_filled = ts.interpolate(interpolation_method="constant")
```

## Visualization

```python
# Create interactive plot
fig = ts.plot(
    title="My Timeseries",
    height=600,
    width=1000,
    line_color="#FF5733",
    line_shape="linear",
    template="plotly_white"
)

# Display or save
fig.show()
# fig.write_html("output/plot.html")
```

## Iteration

```python
# Iterate over rows
for timestamp, value in ts.iter_rows():
    print(f"{timestamp}: {value}")
```

## Properties

```python
# Access timeseries properties
frequency = ts.frequency  # pendulum.Duration
timestep = ts.timestep    # same as frequency
timezone = ts.timezone    # timezone string
shape = ts.shape          # (rows, columns)
```

For more information, see the [API Reference](../api/math/timeseries.md).
