"""Tests for the Timeseries class using pytest.

This module provides comprehensive tests for the Timeseries wrapper class
that uses the Polars backend for time series data manipulation.
"""

import os
import pickle
import tempfile
from datetime import datetime, timedelta

import pandas as pd
import pendulum
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
        assert isinstance(ts.to_frame(), pl.DataFrame)
        assert len(ts) == 4
        assert "time" in ts.to_frame().columns

    def test_init_with_pandas_df(self, sample_pandas_df):
        """Test initialization with a pandas DataFrame."""
        ts = Timeseries(sample_pandas_df)
        assert isinstance(ts.to_frame(), pl.DataFrame)
        assert len(ts) == 4
        assert "time" in ts.to_frame().columns

    def test_from_index(self):
        start = "2025-01-01 00:00:00"
        end = "2025-01-01 02:00:00"
        freq = "1h"

        # Constant default_value
        ts1 = Timeseries.from_index(start, freq, end, default_value=5.0, timezone="UTC")
        assert ts1.shape[0] == 3
        assert ts1.dataframe["value"].to_list() == [5.0, 5.0, 5.0]
        assert ts1.dataframe["time"].to_list() == [
            datetime(2025, 1, 1, 0, 0, 0, tzinfo=Timezone(key="UTC")),
            datetime(2025, 1, 1, 1, 0, 0, tzinfo=Timezone(key="UTC")),
            datetime(2025, 1, 1, 2, 0, 0, tzinfo=Timezone(key="UTC")),
        ]

        # List default_value
        ts2 = Timeseries.from_index(start, freq, end, default_value=[1.0, 2.0, 3.0], timezone="UTC")
        assert ts2.dataframe["value"].to_list() == [1.0, 2.0, 3.0]

    def test_from_timeseries(self):
        start = "2025-01-01 00:00:00"
        end = "2025-01-01 02:00:00"
        freq = "1h"
        ts1 = Timeseries.from_index(start, freq, end, default_value=5.0, timezone="UTC")
        ts2 = Timeseries.from_timeseries(ts1)
        ts3 = Timeseries.from_timeseries(ts1, 0.0)

        assert ts1 == ts2
        assert ts1 != ts3

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
        assert isinstance(ts.to_frame(), pl.DataFrame)
        assert len(ts) == 2
        assert "time" in ts.to_frame().columns

    def test_init_with_timeseries(self, sample_ts):
        """Test initialization with another Timeseries object."""
        ts = Timeseries(sample_ts)
        assert isinstance(ts.to_frame(), pl.DataFrame)
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
        assert ts.frequency == pendulum.duration(hours=1)
        assert len(ts) == 49

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
        assert ts["value"] == [10.0, 20.0, 30.0, 40.0]

    def test_from_file_invalid(self, tmp_path):
        """Test loading from file with filters."""
        # Create a sample CSV file
        # Load with filter
        with pytest.raises(NotImplementedError):
            ts = Timeseries.from_file("invalid_file")

    def test_repr_method(self, sample_ts):
        """Test string representation of Timeseries."""
        repr_str = repr(sample_ts)
        assert "Timeseries" in repr_str
        assert isinstance(repr_str, str)

    def test_timeseries_from_values(self):
        start = "2025-01-01 00:00:00"
        freq = "1h"
        values = [1.0, 2.0, 3.0, 4.0]
        ts = Timeseries.from_values(start, freq, values, timezone="UTC")
        # Check type and shape
        assert isinstance(ts, Timeseries)
        assert len(ts) == 4
        # Check time values
        expected_times = [
            pendulum.datetime(2025, 1, 1, 0, 0, 0, tz="UTC"),
            pendulum.datetime(2025, 1, 1, 1, 0, 0, tz="UTC"),
            pendulum.datetime(2025, 1, 1, 2, 0, 0, tz="UTC"),
            pendulum.datetime(2025, 1, 1, 3, 0, 0, tz="UTC"),
        ]
        assert ts.index == expected_times

        assert ts["value"] == values

        assert ts.timestep == pendulum.duration(hours=1)

    def test_timeseries_from_values_with_datetime(self):
        start = datetime(2025, 1, 1, 0, 0, 0)
        freq = pendulum.duration(hours=1)
        values = [1.0, 2.0, 3.0, 4.0]
        ts = Timeseries.from_values(start, freq, values, timezone="UTC")
        # Check type and shape
        assert isinstance(ts, Timeseries)
        assert len(ts) == 4
        # Check time values
        expected_times = [
            pendulum.datetime(2025, 1, 1, 0, 0, 0, tz="UTC"),
            pendulum.datetime(2025, 1, 1, 1, 0, 0, tz="UTC"),
            pendulum.datetime(2025, 1, 1, 2, 0, 0, tz="UTC"),
            pendulum.datetime(2025, 1, 1, 3, 0, 0, tz="UTC"),
        ]
        assert ts.index == expected_times

        assert ts["value"] == values

        assert ts.timestep == pendulum.duration(hours=1)


class TestTimeseriesBasicOperations:
    """Test basic operations of the Timeseries class."""

    def test_eq(self, sample_ts: Timeseries):
        """Test equality comparison."""
        ts1 = sample_ts
        ts2 = Timeseries(sample_ts.to_frame())
        assert ts1 == ts2

    def test_eq_different(self, sample_ts, sample_df_with_nulls):
        """Test equality comparison with different objects."""
        ts1 = sample_ts
        ts2 = Timeseries(sample_df_with_nulls)
        assert ts1 != ts2

    def test_eq_not_implemented(self, sample_ts):
        """Test equality comparison with unsupported type."""
        with pytest.raises(TypeError, match="Comparison with non-Timeseries objects is not supported"):
            sample_ts == "not a timeseries"

    def test_len(self, sample_ts):
        """Test length calculation."""
        assert len(sample_ts) == 4

    def test_contains_with_datetime(self, sample_ts):
        """Test __contains__ with datetime object."""
        dt_exists = datetime(2023, 1, 1, 1, 0, 0)
        dt_not_exists = datetime(2023, 1, 1, 1, 30, 0)

        assert dt_exists in sample_ts
        assert dt_not_exists not in sample_ts

    def test_contains_with_string(self, sample_ts):
        """Test __contains__ with string datetime."""
        dt_exists = "2023-01-01 02:00:00"
        dt_not_exists = "2023-01-01 04:00:00"

        assert dt_exists in sample_ts
        assert dt_not_exists not in sample_ts

    def test_contains_with_pendulum_datetime(self, sample_ts):
        """Test __contains__ with pendulum.DateTime object."""
        dt_exists = pendulum.datetime(2023, 1, 1, 3, 0, 0, tz="UTC")
        dt_not_exists = pendulum.datetime(2023, 1, 1, 5, 0, 0, tz="UTC")

        assert dt_exists in sample_ts
        assert dt_not_exists not in sample_ts

    def test_contains_with_different_timezone(self, sample_ts):
        """Test __contains__ with datetime in different timezone."""
        # Create a timeseries with Europe/Paris timezone
        sample_ts.set_timezone("Europe/Paris")

        # Test with UTC datetime that corresponds to a time in the series
        # 2023-01-01 00:00:00 UTC = 2023-01-01 01:00:00 Europe/Paris
        dt_utc = pendulum.datetime(2023, 1, 1, 0, 0, 0, tz="UTC")

        # The __contains__ should convert to the timeseries timezone
        assert dt_utc in sample_ts

    def test_contains_with_invalid_input(self, sample_ts):
        """Test __contains__ with invalid input returns False."""
        # Invalid inputs should return False instead of raising an exception
        assert (123 in sample_ts) is False
        assert (None in sample_ts) is False
        assert ([] in sample_ts) is False

    def test_mul_with_value(self, sample_ts):
        """Test multiplication operation between a timeseries and a value."""
        ts = sample_ts * 2
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.dataframe.select(pl.col("value")).to_series()
        new_values = ts.dataframe.select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig * 2

    def test_mul_with_ts(self, sample_ts):
        """Test multiplication operation between two timeseries."""
        ts = sample_ts * sample_ts
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.dataframe.select(pl.col("value")).to_series()
        new_values = ts.dataframe.select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig * orig

    def test_mul_with_ts_wrong_frequency(self, sample_ts):
        """Test multiplication operation between two timeseries."""
        df_with_wrong_frequency = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 0, 0, 0),
                    datetime(2023, 1, 1, 0, 30, 0),
                ],
                "value": [10.0, 20.0],
            },
        )
        ts_with_wrong_frequency = Timeseries(df_with_wrong_frequency)

        with pytest.raises(ValueError):
            sample_ts * ts_with_wrong_frequency

    def test_mul_with_ts_wrong_timestamps(self, sample_ts):
        """Test multiplication operation between two timeseries."""
        df_with_wrong_timstamps = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 4, 0, 0),
                    datetime(2023, 1, 1, 5, 0, 0),
                ],
                "value": [10.0, 20.0],
            },
        )
        ts_with_wrong_timstamps = Timeseries(df_with_wrong_timstamps)

        with pytest.raises(ValueError):
            sample_ts * ts_with_wrong_timstamps

    def test_add_with_value(self, sample_ts):
        """Test add operation between a timeseries and a value."""
        ts = sample_ts + 2
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.dataframe.select(pl.col("value")).to_series()
        new_values = ts.dataframe.select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig + 2

    def test_add_with_ts(self, sample_ts):
        """Test add operation between two timeseries."""
        ts = sample_ts + sample_ts
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.dataframe.select(pl.col("value")).to_series()
        new_values = ts.dataframe.select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig + orig

    pl.DataFrame(
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
    def test_add_with_ts_wrong_frequency(self, sample_ts):
        """Test add operation between two timeseries."""
        df_with_wrong_frequency = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 0, 0, 0),
                    datetime(2023, 1, 1, 0, 30, 0),
                ],
                "value": [10.0, 20.0],
            },
        )
        ts_with_wrong_frequency = Timeseries(df_with_wrong_frequency)

        with pytest.raises(ValueError):
            sample_ts + ts_with_wrong_frequency

    def test_add_with_ts_wrong_timestamps(self, sample_ts):
        """Test add operation between two timeseries."""
        df_with_wrong_timstamps = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 4, 0, 0),
                    datetime(2023, 1, 1, 5, 0, 0),
                ],
                "value": [10.0, 20.0],
            },
        )
        ts_with_wrong_timstamps = Timeseries(df_with_wrong_timstamps)

        with pytest.raises(ValueError):
            sample_ts + ts_with_wrong_timstamps

    def test_sub_with_value(self, sample_ts):
        """Test subtraction operation between a timeseries and a value."""
        ts = sample_ts - 2
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.dataframe.select(pl.col("value")).to_series()
        new_values = ts.dataframe.select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig - 2

    def test_sub_with_ts(self, sample_ts):
        """Test subtraction operation between two timeseries."""
        ts = sample_ts - sample_ts
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.dataframe.select(pl.col("value")).to_series()
        new_values = ts.dataframe.select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig - orig

    def test_sub_with_ts_wrong_frequency(self, sample_ts):
        """Test subtraction operation between two timeseries."""
        df_with_wrong_frequency = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 0, 0, 0),
                    datetime(2023, 1, 1, 0, 30, 0),
                ],
                "value": [10.0, 20.0],
            },
        )
        ts_with_wrong_frequency = Timeseries(df_with_wrong_frequency)

        with pytest.raises(ValueError):
            sample_ts - ts_with_wrong_frequency

    def test_sub_with_ts_wrong_timestamps(self, sample_ts):
        """Test subtraction operation between two timeseries."""
        df_with_wrong_timstamps = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 4, 0, 0),
                    datetime(2023, 1, 1, 5, 0, 0),
                ],
                "value": [10.0, 20.0],
            },
        )
        ts_with_wrong_timstamps = Timeseries(df_with_wrong_timstamps)

        with pytest.raises(ValueError):
            sample_ts - ts_with_wrong_timstamps

    def test_div_with_value(self, sample_ts):
        """Test division operation between a timeseries and a value."""
        ts = sample_ts / 2
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.dataframe.select(pl.col("value")).to_series()
        new_values = ts.dataframe.select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig / 2

    def test_div_with_ts(self, sample_ts):
        """Test division operation between two timeseries."""
        ts = sample_ts / sample_ts
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.dataframe.select(pl.col("value")).to_series()
        new_values = ts.dataframe.select(pl.col("value")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig / orig

    def test_div_with_ts_wrong_frequency(self, sample_ts):
        """Test division operation between two timeseries."""
        df_with_wrong_frequency = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 0, 0, 0),
                    datetime(2023, 1, 1, 0, 30, 0),
                ],
                "value": [10.0, 20.0],
            },
        )
        ts_with_wrong_frequency = Timeseries(df_with_wrong_frequency)

        with pytest.raises(ValueError):
            sample_ts / ts_with_wrong_frequency

    def test_div_with_ts_wrong_timestamps(self, sample_ts):
        """Test division operation between two timeseries."""
        df_with_wrong_timstamps = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 4, 0, 0),
                    datetime(2023, 1, 1, 5, 0, 0),
                ],
                "value": [10.0, 20.0],
            },
        )
        ts_with_wrong_timstamps = Timeseries(df_with_wrong_timstamps)

        with pytest.raises(ValueError):
            sample_ts / ts_with_wrong_timstamps

    def test_div_with_zero_value_ts(self, sample_ts):
        """Test division operation between two timeseries."""
        df_with_zero_value = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 0, 0, 0),
                    datetime(2023, 1, 1, 1, 0, 0),
                ],
                "value": [0.0, 20.0],
            },
        )
        ts_with_zero_value = Timeseries(df_with_zero_value)

        with pytest.raises(ValueError):
            sample_ts / ts_with_zero_value

    def test_set_value(self, sample_ts):

        # Overwrite value
        sample_ts.set_value("2023-01-01 01:00:00", 99, "YYYY-MM-DD HH:mm:ss")

        assert sample_ts["value"] == [10, 99, 30, 40]

    def test_set_value_at_wrong_index(self, sample_ts):
        with pytest.raises(ValueError):
            sample_ts.set_value("2024-01-01 01:00:00", 99, "YYYY-MM-DD HH:mm:ss")

    def test_set_values(self, sample_ts):
        ts = Timeseries.from_timeseries(sample_ts)

        df = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 0, 0, 0),
                    datetime(2023, 1, 1, 1, 0, 0),
                    datetime(2023, 1, 1, 2, 0, 0),
                ],
                "value": [11.0, 21.0, 31.0],
            },
        )
        new_ts = Timeseries(df)
        # Insert new values
        ts.set_values(new_ts)

        assert ts["time"] == [
            datetime(2023, 1, 1, 0, 0, tzinfo=Timezone(key="UTC")),
            datetime(2023, 1, 1, 1, 0, tzinfo=Timezone(key="UTC")),
            datetime(2023, 1, 1, 2, 0, tzinfo=Timezone(key="UTC")),
            datetime(2023, 1, 1, 3, 0, tzinfo=Timezone(key="UTC")),
        ]
        assert ts["value"] == [11, 21, 31, 40]
        assert ts.timestep == pendulum.duration(hours=1)

    def test_if_set_values_with_new_timestamps_then_return_error(self, sample_ts):
        ts = Timeseries.from_timeseries(sample_ts)

        df = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 4, 0, 0),
                    datetime(2023, 1, 1, 5, 0, 0),
                ],
                "value": [51.0, 61.0],
            },
        )
        new_ts = Timeseries(df)

        with pytest.raises(ValueError):
            ts.set_values(new_ts)

    def test_add_value_at(self, sample_ts):
        ts = Timeseries()

        # Insert new values
        ts.add_value_at("2024-01-01 00:00:00", 2, "YYYY-MM-DD HH:mm:ss")  # work if timeseries if empty
        ts.add_value_at("2024-01-01 01:00:00", 4, "YYYY-MM-DD HH:mm:ss")  # work if index has no value

        # Overwrite value
        ts.set_value("2024-01-01 02:00:00", 5, "YYYY-MM-DD HH:mm:ss")
        ts.add_value_at("2024-01-01 02:00:00", 1, "YYYY-MM-DD HH:mm:ss")

        assert ts["time"] == [
            datetime(2024, 1, 1, 0, 0, tzinfo=Timezone(key="UTC")),
            datetime(2024, 1, 1, 1, 0, tzinfo=Timezone(key="UTC")),
            datetime(2024, 1, 1, 2, 0, tzinfo=Timezone(key="UTC")),
        ]
        assert ts["value"] == [2, 4, 6]
        assert ts.timestep == pendulum.duration(hours=1)

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

    def test_sum_methods(self, sample_ts):
        """Test sum methods."""
        assert sample_ts.sum() == 100.0

        # Test with empty Timeseries
        empty_ts = Timeseries()
        assert empty_ts.sum() is None

    def test_interpolate_method(self, sample_df_with_nulls):
        """Test interpolation methods."""
        # Create a Timeseries with null values
        ts = Timeseries(sample_df_with_nulls)

        # Test linear interpolation
        ts_linear = ts.interpolate("linear", inplace=False)
        interpolated_values = ts_linear["value"]

        assert interpolated_values[1] == 20.0

        ts = Timeseries(sample_df_with_nulls)
        # Test constant interpolation (forward fill)
        ts_constant = ts.interpolate("constant", inplace=False)
        interpolated_values = ts_constant["value"]

        # For constant interpolation, the null should be filled with the previous value
        assert interpolated_values[1] == 10.0

    def test_get_lazy(self, sample_ts):
        """Test conversion to LazyFrame."""

        lazy_frame = sample_ts.to_lazy()
        assert isinstance(lazy_frame, pl.LazyFrame)
        assert lazy_frame.collect().equals(sample_ts.dataframe)

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

    def test_to_frame_with_different_engines(self, sample_ts):
        """Test to_frame method with different engines."""
        # Polars engine (default)
        polars_data = sample_ts.to_frame(engine="polars")
        assert isinstance(polars_data, pl.DataFrame)

        # Pandas engine
        pandas_data = sample_ts.to_frame(engine="pandas")
        assert isinstance(pandas_data, pd.DataFrame)

        # Invalid engine
        with pytest.raises(ValueError):
            sample_ts.to_frame(engine="invalid")

    def test_get_value_with_inside_time(self, sample_ts):
        """Test get_value method with a time in the series."""
        # Time between two existing points
        value = sample_ts.get_value(datetime(2023, 1, 1, 1, 0, 0))

        assert value == 20.0

    def test_get_value_with_inside_time_not_in_index(self, sample_ts):
        """Test get_value method with a time not in the series."""
        # Time between two existing points
        with pytest.raises(KeyError):
            sample_ts.get_value(datetime(2023, 1, 1, 1, 0, 1))

    def test_get_value_with_outside_time(self, sample_ts):
        """Test get_value method with a time not in the series."""
        # Time between two existing points
        with pytest.raises(KeyError):
            value = sample_ts.get_value(datetime(2023, 1, 1, 4, 0, 0))

    def test_get_value_on_empty_timeseries(self):
        """Test get_value on an empty Timeseries."""
        ts = Timeseries()
        with pytest.raises(ValueError):
            value = ts.get_value(datetime(2023, 1, 1))

    def test_properties_shape(self, sample_ts: Timeseries):
        """Test the shape and index properties of Timeseries."""
        # Test shape
        shape = sample_ts.shape
        expected_shape = (4, 2)  # Assuming sample_ts has 4 rows and 2 columns (time + one value)
        assert shape == expected_shape, f"Expected shape {expected_shape}, got {shape}"

    def test_properties_frequency(self, sample_ts: Timeseries):
        """Test the shape and index properties of Timeseries."""
        # Test shape
        freq = sample_ts.frequency

        assert freq == pendulum.duration(hours=1), f"Expected shape {pendulum.duration(hours=1)}, got {freq}"

    def test_properties_index(self, sample_ts: Timeseries):
        # Test index
        index = sample_ts.index
        expected_shape = (4, 2)
        assert isinstance(index, list)
        assert all(isinstance(ts, datetime) for ts in index)
        assert len(index) == expected_shape[0]

    def test_set_frequency(self, sample_ts):
        sample_ts_copy = Timeseries(sample_ts)
        sample_ts.set_frequency(pendulum.duration(minutes=30))
        freq = sample_ts.timestep

        assert freq == pendulum.duration(minutes=30), f"Expected shape {pendulum.duration(minutes=30)}, got {freq}"

        sample_ts.set_frequency("1h")
        freq = sample_ts.timestep

        assert freq == pendulum.duration(hours=1), f"Expected shape {pendulum.duration(hours=1)}, got {freq}"

        assert sample_ts == sample_ts_copy

    def test_first_date(self, sample_ts):
        assert sample_ts.first_date() == datetime(2023, 1, 1, 0, 0, 0, tzinfo=Timezone("UTC"))

    def test_last_date(self, sample_ts):
        assert sample_ts.last_date() == datetime(2023, 1, 1, 3, 0, 0, tzinfo=Timezone("UTC"))

    def test_iter_rows(self, sample_ts):
        """Test iterating over rows of the Timeseries."""
        rows = list(sample_ts.iter_rows())

        # Check that we get the correct number of rows
        assert len(rows) == 4

        # Check that each row is a tuple of (time, value)
        assert all(isinstance(row, tuple) and len(row) == 2 for row in rows)

        # Check the first row
        assert rows[0][0] == datetime(2023, 1, 1, 0, 0, 0, tzinfo=Timezone("UTC"))
        assert rows[0][1] == 10.0

        # Check the last row
        assert rows[-1][0] == datetime(2023, 1, 1, 3, 0, 0, tzinfo=Timezone("UTC"))
        assert rows[-1][1] == 40.0

        # Check all values
        expected_values = [10.0, 20.0, 30.0, 40.0]
        actual_values = [row[1] for row in rows]
        assert actual_values == expected_values

        # Test that iter_rows returns an iterable
        rows_iterator = sample_ts.iter_rows()
        first_row = next(rows_iterator)
        assert first_row == (datetime(2023, 1, 1, 0, 0, 0, tzinfo=Timezone("UTC")), 10.0)


class TestTimeseriesManipulation:
    """Test time series manipulation methods."""

    def test_upsample_linear(self, sample_ts):
        """Test upsampling with linear interpolation."""
        original_len = len(sample_ts)
        upsampled = sample_ts.upsample("30m", "linear", inplace=False)

        # Should have more rows now
        assert len(upsampled) > original_len

        # Check if upsampled correctly
        time_diffs = [
            (t2 - t1).total_seconds() / 60
            for t1, t2 in zip(
                upsampled["time"][:-1],
                upsampled["time"][1:],
                strict=False,
            )
        ]

        # All time differences should be 30 minutes
        assert all(diff == 30 for diff in time_diffs)

    def test_upsample_constant(self, sample_ts):
        """Test upsampling with constant fill."""
        upsampled = sample_ts.upsample("30m", "constant", inplace=False)

        # Check if values are forward-filled
        times = upsampled["time"]
        values = upsampled["value"]

        # For each original time point, check next 30-min point has same value
        for i in range(len(sample_ts) - 1):
            orig_time = sample_ts["time"][i]
            orig_value = sample_ts["value"][i]

            # Find the next 30-min point in upsampled data
            next_time_idx = times.index(orig_time) + 1
            next_value = values[next_time_idx]

            assert next_value == orig_value  # Should be forward-filled

    def test_upsample_constant_with_timedelta(self, sample_ts):
        """Test upsampling with constant fill."""
        upsampled = sample_ts.upsample(timedelta(minutes=30), "constant", inplace=False)

        # Check if values are forward-filled
        times = upsampled["time"]
        values = upsampled["value"]

        # For each original time point, check next 30-min point has same value
        for i in range(len(sample_ts) - 1):
            orig_time = sample_ts["time"][i]
            orig_value = sample_ts["value"][i]

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
        actual_means = grouped["value"]

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
        actual_sums = grouped["value"]

        assert actual_sums == expected_sums

    def test_groupby_with_invalid_agg(self, sample_ts):
        """Test grouping with an invalid aggregation function."""
        with pytest.raises(NotImplementedError):
            sample_ts.groupby("1h", agg="invalid")

    def test_join(self, sample_ts):
        """Test joining with another time series."""
        # Create another time series
        other_df = pl.DataFrame(
            {
                "time": [
                    datetime(2023, 1, 1, 0, 0, 0),
                    datetime(2023, 1, 1, 0, 30, 0),
                    datetime(2023, 1, 1, 1, 0, 0),
                    datetime(2023, 1, 1, 1, 30, 0),
                ],
                "value3": [1000, 2000, 3000, 5000],
            },
        )
        other_ts = Timeseries(other_df)

        # Test inner join
        joined = sample_ts._join(other_ts, by="time", how="inner")
        assert len(joined) == 2  # Only matching times
        assert joined.columns == ["time", "value", "value_right"]

        # Test left join
        left_joined = sample_ts._join(other_ts, by="time", how="left")
        assert len(left_joined) == 4
        assert left_joined["value_right"].to_list() == [1000, 3000, None, None]

    def test_timezone_operations(self, sample_ts):
        """Test timezone conversion operations."""
        ts = sample_ts
        assert ts.timezone == "UTC"

        # Change timezone
        ts.set_timezone("America/New_York")
        assert ts.timezone == "America/New_York"

        # Verify times are converted
        times = ts["time"]
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
        assert result["value"][0] == 10

    def test_filter_with_datetime_pendulum(self, sample_ts):
        dt = pendulum.datetime(2023, 1, 1, 0, 0, 0)
        result = sample_ts.filter(dt, inplace=False)
        assert len(result) == 1
        assert result["value"][0] == 10

    def test_filter_with_list_of_datetime(self, sample_ts):
        dts = [datetime(2023, 1, 1, 0, 0, 0), datetime(2023, 1, 1, 1, 0, 0)]
        result = sample_ts.filter(dts, inplace=False)
        assert len(result) == 2
        assert result["value"] == [10, 20]

    def test_filter_with_str(self, sample_ts):
        result = sample_ts.filter("2023-01-01 03:00:00", "YYYY-MM-DD HH:mm:ss", inplace=False)
        assert len(result) == 1
        assert result["value"] == [40]

    def test_filter_invalid(self, sample_ts):
        with pytest.raises(TypeError):
            result = sample_ts.filter(2, inplace=False)

    def test_slice_with_datetime(self, sample_ts):
        result = sample_ts.slice(datetime(2023, 1, 1, 1, 0, 0), datetime(2023, 1, 1, 2, 0, 0), inplace=False)
        result_exclude = sample_ts.slice(
            datetime(2023, 1, 1, 1, 0, 0), datetime(2023, 1, 1, 3, 0, 0), closed="none", inplace=False
        )
        assert len(result) == 2
        assert result["value"][0] == 20
        assert result["value"][1] == 30
        assert len(result_exclude) == 1
        assert result_exclude["value"][0] == 30

    def test_slice_with_int(self, sample_ts):
        result = sample_ts.slice_with_offset(1, 2, inplace=False)
        assert len(result) == 2
        assert result["value"][0] == 20
        assert result["value"][1] == 30

    def test_get_value(self, sample_ts):
        """Test getting a value at a specific timestamp."""
        dt = datetime(2023, 1, 1, 1, 0, 0)
        value = sample_ts.get_value(dt)
        assert value == 20.0

        date_format = "YYYY-MM-DD HH:mm:ss"
        value = sample_ts.get_value("2023-01-01 03:00:00", date_format=date_format)
        assert value == 40.0


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
