"""Tests for the Timeseries class using pytest.

This module provides comprehensive tests for the Timeseries wrapper class
that uses the Polars backend for time series data manipulation.
"""

import os
import pickle
import tempfile
from datetime import datetime, timedelta

import pandas as pd
import polars as pl
import pytest
from pendulum import Timezone

from atlas import Timeseries


@pytest.fixture
def sample_df() -> pl.DataFrame:
    """Create a sample DataFrame for testing."""
    return pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0, 0),
                datetime(2023, 1, 1, 1, 0, 0),
                datetime(2023, 1, 1, 2, 0, 0),
                datetime(2023, 1, 1, 3, 0, 0),
            ],
            "value": [10.0, 20.0, 30.0, 40.0],
        },
    )


@pytest.fixture
def sample_ts(sample_df) -> Timeseries:
    """Create a sample Timeseries instance for testing."""
    return Timeseries(sample_df)


@pytest.fixture
def sample_df_with_nulls() -> pl.DataFrame:
    """Create a sample DataFrame with null values for testing."""
    return pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0, 0),
                datetime(2023, 1, 1, 1, 0, 0),
                datetime(2023, 1, 1, 2, 0, 0),
                datetime(2023, 1, 1, 3, 0, 0),
            ],
            "value": [10.0, None, 30.0, 40.0],
        },
    )


@pytest.fixture
def sample_pandas_df() -> pd.DataFrame:
    """Create a sample pandas DataFrame for testing."""
    return pd.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0, 0),
                datetime(2023, 1, 1, 1, 0, 0),
                datetime(2023, 1, 1, 2, 0, 0),
                datetime(2023, 1, 1, 3, 0, 0),
            ],
            "value": [10.0, 20.0, 30.0, 40.0],
        },
    )


class TestTimeseriesInit:
    """Test initialization of the Timeseries class."""

    def test_init_with_polars_df(self, sample_df):
        """Test initialization with a Polars DataFrame."""
        ts = Timeseries(sample_df)
        assert isinstance(ts.get_data(), pl.DataFrame)
        assert len(ts) == 4
        assert "time" in ts.get_data().columns

    def test_init_with_pandas_df(self, sample_pandas_df):
        """Test initialization with a pandas DataFrame."""
        ts = Timeseries(sample_pandas_df)
        assert isinstance(ts.get_data(), pl.DataFrame)
        assert len(ts) == 4
        assert "time" in ts.get_data().columns

    def test_init_with_dict(self):
        """Test initialization with a dictionary."""
        data = {
            "time": [
                datetime(2023, 1, 1, 0, 0, 0),
                datetime(2023, 1, 1, 1, 0, 0),
            ],
            "value": [10.0, 20.0],
        }
        ts = Timeseries(data)
        assert isinstance(ts.get_data(), pl.DataFrame)
        assert len(ts) == 2
        assert "time" in ts.get_data().columns

    def test_init_with_timeseries(self, sample_ts):
        """Test initialization with another Timeseries object."""
        ts = Timeseries(sample_ts)
        assert isinstance(ts.get_data(), pl.DataFrame)
        assert len(ts) == 4
        assert ts == sample_ts

    def test_init_with_timezone(self, sample_df):
        """Test initialization with a specific timezone."""
        ts = Timeseries(sample_df, timezone="Europe/Paris")
        assert ts.timezone == "Europe/Paris"

    def test_init_invalid_data(self):
        """Test initialization with invalid data."""
        with pytest.raises(ValueError):
            Timeseries("not a dataframe")

    def test_init_no_datetime_column(self):
        """Test initialization with data that has no datetime column."""
        df = pl.DataFrame(
            {
                "a": [1, 2, 3],
                "b": [4, 5, 6],
            },
        )
        with pytest.raises(ValueError):
            Timeseries(df)

    def test_init_multiple_datetime_columns(self):
        """Test initialization with data that has multiple datetime columns."""
        df = pl.DataFrame(
            {
                "time1": [datetime(2023, 1, 1, 0, 0, 0), datetime(2023, 1, 1, 1, 0, 0)],
                "time2": [datetime(2023, 1, 1, 0, 0, 0), datetime(2023, 1, 1, 1, 0, 0)],
                "value": [10.0, 20.0],
            },
        )
        with pytest.raises(ValueError):
            Timeseries(df)

    def test_invalid_timezone(self):
        """Test initialization with an invalid timezone."""
        with pytest.raises(ValueError):
            Timeseries(None, "invalid_timezone")

    def test_from_file_with_filters(self, tmp_path):
        """Test loading from file with filters."""
        # Create a sample CSV file
        csv_path = tmp_path / "test_data.csv"
        df = pl.DataFrame(
            {
                "category": ["A", "B", "A", "C"],
                "time": [
                    datetime(2023, 1, 1),
                    datetime(2023, 1, 2),
                    datetime(2023, 1, 3),
                    datetime(2023, 1, 4),
                ],
                "value": [10.0, 20.0, 30.0, 40.0],
            }
        )
        df.write_csv(csv_path, separator=";")

        # Load with filter
        ts = Timeseries.from_file(csv_path, filters=("category", "A"))

        # Should only have rows where category is "A"
        assert len(ts) == 2
        assert ts.get_data()["value"].to_list() == [10.0, 30.0]

    def test_describe(self):
        df = pl.DataFrame(
            {
                "category": ["A", "B", "A", "C"],
                "time": [
                    datetime(2023, 1, 1),
                    datetime(2023, 1, 2),
                    datetime(2023, 1, 3),
                    datetime(2023, 1, 4),
                ],
                "value": [10.0, 20.0, 30.0, 40.0],
            }
        )

        metadata = Timeseries.describe(timeseries=df)

        assert metadata == {
            "shape": (4, 3),
            "memory_mb": "0.00",
            "datetime": {
                "column": "time",
                "min": "2023-01-01 00:00:00",
                "max": "2023-01-04 00:00:00",
                "nulls": 0,
            },
            "categorical": {"column": "category", "categories": ["A", "B", "C"], "nulls": 0},
            "numerical": {"column": "value", "nulls": 0, "min": 10.0, "max": 40.0},
        }

    def test_from_file_parquet(self, tmp_path):
        """Test loading from file with filters."""
        # Create a sample CSV file
        parquet_path = tmp_path / "test_data.parquet"
        df = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1),
                    datetime(2023, 1, 2),
                    datetime(2023, 1, 3),
                    datetime(2023, 1, 4),
                ],
                "value": [10.0, 20.0, 30.0, 40.0],
            }
        )
        df.write_parquet(parquet_path)

        ts = Timeseries.from_file(parquet_path)

        assert len(ts) == 4
        assert ts.get_data()["value"].to_list() == [10.0, 20.0, 30.0, 40.0]

    def test_from_file_invalid(self, tmp_path):
        """Test loading from file with filters."""
        # Create a sample CSV file
        # Load with filter
        with pytest.raises(ValueError, match="Unsupported file format. Only CSV and Parquet are supported."):
            ts = Timeseries.from_file("invalid_file")

    def test_repr_method(self, sample_ts):
        """Test string representation of Timeseries."""
        repr_str = repr(sample_ts)
        assert "Timeseries" in repr_str
        assert isinstance(repr_str, str)


class TestTimeseriesBasicOperations:
    """Test basic operations of the Timeseries class."""

    def test_eq(self, sample_ts: Timeseries):
        """Test equality comparison."""
        ts1 = sample_ts
        ts2 = Timeseries(sample_ts.get_data())
        assert ts1 == ts2

    def test_eq_different(self, sample_ts, sample_df_with_nulls):
        """Test equality comparison with different objects."""
        ts1 = sample_ts
        ts2 = Timeseries(sample_df_with_nulls)
        assert ts1 != ts2

    def test_eq_not_implemented(self, sample_ts):
        """Test equality comparison with unsupported type."""
        with pytest.raises(NotImplementedError):
            sample_ts == "not a timeseries"

    def test_len(self, sample_ts):
        """Test length calculation."""
        assert len(sample_ts) == 4

    def test_mul_with_value(self, sample_ts):
        """Test multiplication operation between a timeseries and a value."""
        ts = sample_ts * 2
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.get_data().select(pl.col("value")).to_series()
        new_values = ts.get_data().select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig * 2

    def test_mul_with_ts(self, sample_ts):
        """Test multiplication operation between two timeseries."""
        ts = sample_ts * sample_ts
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.get_data().select(pl.col("value")).to_series()
        new_values = ts.get_data().select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig * orig

    def test_add_with_value(self, sample_ts):
        """Test add operation between a timeseries and a value."""
        ts = sample_ts + 2
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.get_data().select(pl.col("value")).to_series()
        new_values = ts.get_data().select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig + 2

    def test_add_with_ts(self, sample_ts):
        """Test add operation between two timeseries."""
        ts = sample_ts + sample_ts
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.get_data().select(pl.col("value")).to_series()
        new_values = ts.get_data().select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig + orig

    def test_sub_with_value(self, sample_ts):
        """Test substraction operation between a timeseries and a value."""
        ts = sample_ts - 2
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.get_data().select(pl.col("value")).to_series()
        new_values = ts.get_data().select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig - 2

    def test_sub_with_ts(self, sample_ts):
        """Test substraction operation between two timeseries."""
        ts = sample_ts - sample_ts
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.get_data().select(pl.col("value")).to_series()
        new_values = ts.get_data().select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig - orig

    def test_div_with_value(self, sample_ts):
        """Test division operation between a timeseries and a value."""
        ts = sample_ts / 2
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.get_data().select(pl.col("value")).to_series()
        new_values = ts.get_data().select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig / 2

    def test_div_with_ts(self, sample_ts):
        """Test division operation between two timeseries."""
        ts = sample_ts / sample_ts
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.get_data().select(pl.col("value")).to_series()
        new_values = ts.get_data().select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig / orig

    def test_set_value(self, sample_ts):
        ts = Timeseries()

        # Insert new values
        ts.set_value("2024-01-01 00:00:00", 10, "YYYY-MM-DD HH:mm:ss")
        ts.set_value("2024-01-01 01:00:00", 20, "YYYY-MM-DD HH:mm:ss")

        # Overwrite value
        ts.set_value("2024-01-01 01:00:00", 99, "YYYY-MM-DD HH:mm:ss")

        assert ts.get_data()["time"].to_list() == [
            datetime(2024, 1, 1, 0, 0, tzinfo=Timezone(key="UTC")),
            datetime(2024, 1, 1, 1, 0, tzinfo=Timezone(key="UTC")),
        ]
        assert ts.get_data()["value"].to_list() == [10, 99]

    def test_generate_datetimes(self):
        """Test static method to generate datetime range."""
        start = datetime(2023, 1, 1, 0, 0)
        end = datetime(2023, 1, 1, 6, 0)
        step = "2h"

        result = Timeseries.generate_datetimes(start=start, end=end, freq=step)
        expected = [
            datetime(2023, 1, 1, 0, 0, tzinfo=Timezone("UTC")),
            datetime(2023, 1, 1, 2, 0, tzinfo=Timezone("UTC")),
            datetime(2023, 1, 1, 4, 0, tzinfo=Timezone("UTC")),
            datetime(2023, 1, 1, 6, 0, tzinfo=Timezone("UTC")),
        ]

        assert result == expected

    def test_arithmetic_operations_with_invalid_types(self, sample_ts):
        """Test arithmetic operations with invalid types."""
        # Test multiplication
        with pytest.raises(TypeError):
            sample_ts * "invalid"

        # Test addition
        with pytest.raises(TypeError):
            sample_ts + "invalid"

        # Test subtraction
        with pytest.raises(TypeError):
            sample_ts - "invalid"

        # Test division
        with pytest.raises(TypeError):
            sample_ts / "invalid"

    def test_division_by_zero(self, sample_ts):
        """Test division by zero."""
        with pytest.raises(ZeroDivisionError):
            sample_ts / 0

    def test_min_methods(self, sample_ts):
        """Test min methods."""
        assert sample_ts.min() == 10.0

        # Test with empty Timeseries
        empty_ts = Timeseries()
        assert empty_ts.min() is None

    def test_max_methods(self, sample_ts):
        """Test max methods."""
        assert sample_ts.max() == 40.0

        # Test with empty Timeseries
        empty_ts = Timeseries()
        assert empty_ts.max() is None

    def test_interpolate_method(self, sample_df_with_nulls):
        """Test interpolation methods."""
        # Create a Timeseries with null values
        ts = Timeseries(sample_df_with_nulls)

        # Test linear interpolation
        ts_linear = ts.interpolate(method="linear", inplace=False)
        interpolated_values = ts_linear.get_data()["value"].to_list()

        # For linear interpolation between 10.0 and 30.0 with a null in between
        # The interpolated value should be 20.0
        assert interpolated_values[1] == 20.0

        # Test constant interpolation (forward fill)
        ts_constant = ts.interpolate(method="constant", inplace=False)
        interpolated_values = ts_constant.get_data()["value"].to_list()

        # For constant interpolation, the null should be filled with the previous value
        assert interpolated_values[1] == 10.0

    def test_interpolate_invalid_method(self, sample_ts):
        """Test interpolation with an invalid method."""
        with pytest.raises(NotImplementedError):
            sample_ts.interpolate(method="invalid")

    def test_get_lazy(self, sample_ts):
        """Test conversion to LazyFrame."""

        lazy_frame = sample_ts.to_lazy()
        assert isinstance(lazy_frame, pl.LazyFrame)
        assert lazy_frame.collect().equals(sample_ts.get_data())

    def test_generate_datetimes_with_different_freq(self):
        """Test generating datetimes with different frequencies."""
        # Test minute frequency
        start = datetime(2023, 1, 1, 0, 0)
        end = datetime(2023, 1, 1, 0, 10)
        result_minutes = Timeseries.generate_datetimes(start, end, freq="5m")
        assert len(result_minutes) == 3  # 0:00, 0:05, 0:10

        # Test daily frequency
        start = datetime(2023, 1, 1)
        end = datetime(2023, 1, 5)
        result_days = Timeseries.generate_datetimes(start, end, freq="1d")
        assert len(result_days) == 5  # 1st, 2nd, 3rd, 4th, 5th

    def test_generate_datetimes_invalid_freq(self):
        """Test generating datetimes with an invalid frequency."""
        start = datetime(2023, 1, 1)
        end = datetime(2023, 1, 5)

        with pytest.raises(ValueError):
            Timeseries.generate_datetimes(start, end, freq="1y")  # Unsupported frequency

    def test_set_interpolation_method(self, sample_ts):
        """Test setting interpolation method."""
        # Initial method should be 'constant'
        assert sample_ts.interpolation_method == "constant"

        # Change to linear
        sample_ts.set_interpolation_method("linear")
        assert sample_ts.interpolation_method == "linear"

        # Try an invalid method
        with pytest.raises(NotImplementedError):
            sample_ts.set_interpolation_method("invalid")

    def test_plot_method(self, sample_ts):
        """Test plot method returns a Plotly figure."""
        fig = sample_ts.plot()

        # Check Plotly figure attributes
        assert hasattr(fig, "data")
        assert hasattr(fig, "layout")
        assert len(fig.data) > 0

        # Additional plot configurations
        custom_fig = sample_ts.plot(
            title="Custom Plot",
            height=600,
            width=1000,
            show_grid=False,
            line_color="red",
            line_shape="spline",
            template="plotly_dark",
        )
        assert custom_fig.layout.title.text == "Custom Plot"
        assert custom_fig.layout.height == 600
        assert custom_fig.layout.width == 1000

    def test_get_data_with_different_engines(self, sample_ts):
        """Test get_data method with different engines."""
        # Polars engine (default)
        polars_data = sample_ts.get_data(engine="polars")
        assert isinstance(polars_data, pl.DataFrame)

        # Pandas engine
        pandas_data = sample_ts.get_data(engine="pandas")
        assert isinstance(pandas_data, pd.DataFrame)

        # Invalid engine
        with pytest.raises(ValueError):
            sample_ts.get_data(engine="invalid")

    def test_get_value_with_nonexistent_time(self, sample_ts):
        """Test get_value method with a time not in the series."""
        # Time between two existing points
        value = sample_ts.get_value(datetime(2023, 1, 1, 1, 30, 0))

        # Should interpolate (since interpolation method is 'constant')
        assert value == 20.0

    def test_get_value_on_empty_timeseries(self):
        """Test get_value on an empty Timeseries."""
        ts = Timeseries()
        value = ts.get_value(datetime(2023, 1, 1))
        assert value == {"time": datetime(2023, 1, 1), "value": None}


class TestTimeseriesManipulation:
    """Test time series manipulation methods."""

    def test_remove_na(self, sample_df_with_nulls):
        """Test removal of null values."""
        ts = Timeseries(sample_df_with_nulls)
        assert len(ts) == 4

        ts_cleaned = ts.remove_na(inplace=False)
        assert len(ts_cleaned) == 3  # Only rows with no nulls remain
        assert len(ts) == 4  # Original unchanged

        ts.remove_na(inplace=True)
        assert len(ts) == 3  # Now original is changed

    def test_upsample_linear(self, sample_ts):
        """Test upsampling with linear interpolation."""
        original_len = len(sample_ts)
        sample_ts.set_interpolation_method("linear")
        upsampled = sample_ts.upsample("30m", inplace=False)

        # Should have more rows now
        assert len(upsampled) > original_len

        # Check if upsampled correctly
        time_diffs = [
            (t2 - t1).total_seconds() / 60
            for t1, t2 in zip(
                upsampled.get_data()["time"][:-1],
                upsampled.get_data()["time"][1:],
                strict=False,
            )
        ]

        # All time differences should be 30 minutes
        assert all(diff == 30 for diff in time_diffs)

    def test_upsample_constant(self, sample_ts):
        """Test upsampling with constant fill."""
        sample_ts.set_interpolation_method("constant")
        upsampled = sample_ts.upsample("30m", inplace=False)

        # Check if values are forward-filled
        times = upsampled.get_data()["time"].to_list()
        values = upsampled.get_data()["value"].to_list()

        # For each original time point, check next 30-min point has same value
        for i in range(len(sample_ts) - 1):
            orig_time = sample_ts.get_data()["time"][i]
            orig_value = sample_ts.get_data()["value"][i]

            # Find the next 30-min point in upsampled data
            next_time_idx = times.index(orig_time) + 1
            next_value = values[next_time_idx]

            assert next_value == orig_value  # Should be forward-filled

    def test_groupby(self, sample_ts):
        """Test grouping by time intervals."""
        # Create a longer time series with more data points
        times = [datetime(2023, 1, 1) + timedelta(hours=i) for i in range(24)]
        values = list(range(24))
        df = pl.DataFrame({"time": times, "value": values})
        ts = Timeseries(df)

        # Group by 6 hours with mean aggregation
        grouped = ts.groupby("6h", agg="mean", inplace=False)

        # Should have 4 groups (24h / 6h)
        assert len(grouped) == 4

        # Check values (0+1+2+3+4+5)/6, (6+7+8+9+10+11)/6, etc.
        expected_means = [2.5, 8.5, 14.5, 20.5]  # Mean of each 6h group
        actual_means = grouped.get_data()["value"].to_list()

        assert actual_means == pytest.approx(expected_means)

    def test_groupby_with_timedelta(self, sample_ts):
        """Test grouping by timedelta object."""
        # Create a longer time series with more data points
        times = [datetime(2023, 1, 1) + timedelta(hours=i) for i in range(24)]
        values = list(range(24))
        df = pl.DataFrame({"time": times, "value": values})
        ts = Timeseries(df)

        # Group by 6 hours with sum aggregation
        grouped = ts.groupby(timedelta(hours=6), agg="sum", inplace=False)

        # Should have 4 groups (24h / 6h)
        assert len(grouped) == 4

        # Check values (0+1+2+3+4+5), (6+7+8+9+10+11), etc.
        expected_sums = [15, 51, 87, 123]  # Sum of each 6h group
        actual_sums = grouped.get_data()["value"].to_list()

        assert actual_sums == expected_sums

    def test_groupby_with_invalid_agg(self, sample_ts):
        """Test grouping with an invalid aggregation function."""
        with pytest.raises(NotImplementedError):
            sample_ts.groupby("1h", agg="invalid")

    def test_remove_duplicated(self, sample_df):
        """Test removal of duplicated rows."""
        # Create data with duplicates
        df_with_dupes = pl.concat([sample_df, sample_df.slice(0, 2)])
        ts = Timeseries(df_with_dupes)
        assert len(ts) == 6  # 4 original + 2 duplicated

        # Remove duplicates based on time
        deduped = ts.remove_duplicated("time", inplace=False)
        assert len(deduped) == 4  # Back to original size

        # Original unchanged
        assert len(ts) == 6

        # Test inplace
        ts.remove_duplicated("time", inplace=True)
        assert len(ts) == 4

    def test_join(self, sample_ts):
        """Test joining with another time series."""
        # Create another time series
        other_df = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 0, 0, 0),
                    datetime(2023, 1, 1, 1, 0, 0),
                    datetime(2023, 1, 1, 2, 0, 0),
                    datetime(2023, 1, 1, 4, 0, 0),  # Note: this time doesn't exist in sample_ts
                ],
                "value3": [1000, 2000, 3000, 5000],
            },
        )
        other_ts = Timeseries(other_df)

        # Test inner join
        joined = sample_ts._join(other_ts, by="time", how="inner")
        assert len(joined) == 3  # Only matching times
        assert set(joined.columns) == {"time", "value", "value_right"}

        # Test left join
        left_joined = sample_ts._join(other_ts, by="time", how="left")
        assert len(left_joined) == 4  # All rows from sample_ts
        assert left_joined["value_right"][3] is None  # Missing value for 3:00

    def test_timezone_operations(self, sample_ts):
        """Test timezone conversion operations."""
        ts = sample_ts
        assert ts.timezone == "UTC"

        # Change timezone
        ts.set_timezone("America/New_York")
        assert ts.timezone == "America/New_York"

        # Verify times are converted
        times = ts.get_data()["time"].to_list()
        for t in times:
            assert t.tzinfo is not None
            assert "America/New_York" in str(t.tzinfo)

    def test_invalid_timezone_conversion(self, sample_ts):
        """Test conversion to an invalid timezone."""
        with pytest.raises(ValueError):
            sample_ts.set_timezone("Invalid/Timezone")

    def test_filter_with_datetime(self, sample_ts):
        dt = datetime(2023, 1, 1, 0, 0, 0)
        result = sample_ts.filter(dt, inplace=False)
        assert len(result) == 1
        assert result.get_data()["value"].item() == 10

    def test_filter_with_list_of_datetime(self, sample_ts):
        dts = [datetime(2023, 1, 1, 0, 0, 0), datetime(2023, 1, 1, 1, 0, 0)]
        result = sample_ts.filter(dts, inplace=False)
        assert len(result) == 2
        assert result.get_data()["value"].to_list() == [10, 20]

    def test_filter_with_str(self, sample_ts):
        result = sample_ts.filter("2023-01-01 03:00:00", "YYYY-MM-DD HH:mm:ss", inplace=False)
        assert len(result) == 1
        assert result.get_data()["value"].item() == 40

    def test_get_value(self, sample_ts):
        """Test getting a value at a specific timestamp."""
        ts = Timeseries()

        date_format = "YYYY-MM-DD HH:mm:ss"
        # Insert new values
        ts.set_value("2024-01-01 00:00:00", 10, date_format=date_format)
        ts.set_value("2024-01-01 01:00:00", 20, date_format=date_format)
        ts.set_value("2024-01-01 02:00:00", 100, date_format=date_format)
        ts.set_value("2024-01-01 04:00:00", 200, date_format=date_format)
        ts.set_value("2024-01-01 06:00:00", 400, date_format=date_format)

        dt = datetime(2024, 1, 1, 1, 0, 0)
        value = ts.get_value(dt)
        assert value == 20.0

        value = ts.get_value("2024-01-01 03:00:00", date_format=date_format)
        assert value == 100


class TestTimeseriesExport:
    """Test to_fileing time series data."""

    def test_to_file_csv(self, sample_ts):
        """Test to_fileing to CSV format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.csv")
            sample_ts.to_file(path, file_format="csv")
            assert os.path.exists(path)

            # Check if file is readable
            df = pl.read_csv(path)
            assert len(df) == len(sample_ts)

    def test_to_file_parquet(self, sample_ts):
        """Test to_fileing to Parquet format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.parquet")
            sample_ts.to_file(path, file_format="parquet")
            assert os.path.exists(path)

            # Check if file is readable
            df = pl.read_parquet(path)
            assert len(df) == len(sample_ts)

    def test_to_file_pickle(self, sample_ts):
        """Test to_fileing to Pickle format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.pickle")
            sample_ts.to_file(path, file_format="pickle")
            assert os.path.exists(path)

            # Check if file is readable
            with open(path, "rb") as f:
                loaded_ts = pickle.load(f)
            assert isinstance(loaded_ts, Timeseries)
            assert len(loaded_ts) == len(sample_ts)

    def test_to_file_format_mismatch(self, sample_ts):
        """Test to_fileing with a format that doesn't match the file extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with pytest.raises(ValueError):
                sample_ts.to_file(path, file_format="csv")

    def test_to_file_unsupported_format(self, sample_ts):
        """Test to_fileing with an unsupported format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            with pytest.raises(NotImplementedError):
                sample_ts.to_file(path, file_format="json")
