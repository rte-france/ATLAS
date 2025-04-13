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

# Assuming the Timeseries class is in a module named timeseries
from atlas import Timeseries


@pytest.fixture
def sample_df():
    """Create a sample DataFrame for testing."""
    return pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0, 0),
                datetime(2023, 1, 1, 1, 0, 0),
                datetime(2023, 1, 1, 2, 0, 0),
                datetime(2023, 1, 1, 3, 0, 0),
            ],
            "value1": [10.0, 20.0, 30.0, 40.0],
            "value2": [100, 200, 300, 400],
        },
    )


@pytest.fixture
def sample_ts(sample_df):
    """Create a sample Timeseries instance for testing."""
    return Timeseries(sample_df)


@pytest.fixture
def sample_df_with_nulls():
    """Create a sample DataFrame with null values for testing."""
    return pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0, 0),
                datetime(2023, 1, 1, 1, 0, 0),
                datetime(2023, 1, 1, 2, 0, 0),
                datetime(2023, 1, 1, 3, 0, 0),
            ],
            "value1": [10.0, None, 30.0, 40.0],
            "value2": [100, 200, None, 400],
        },
    )


@pytest.fixture
def sample_pandas_df():
    """Create a sample pandas DataFrame for testing."""
    return pd.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0, 0),
                datetime(2023, 1, 1, 1, 0, 0),
                datetime(2023, 1, 1, 2, 0, 0),
                datetime(2023, 1, 1, 3, 0, 0),
            ],
            "value1": [10.0, 20.0, 30.0, 40.0],
            "value2": [100, 200, 300, 400],
        },
    )


class TestTimeseriesInit:
    """Test initialization of the Timeseries class."""

    def test_init_with_polars_df(self, sample_df):
        """Test initialization with a Polars DataFrame."""
        ts = Timeseries(sample_df)
        assert isinstance(ts.get_timeseries(), pl.DataFrame)
        assert len(ts) == 4
        assert "time" in ts.get_timeseries().columns

    def test_init_with_pandas_df(self, sample_pandas_df):
        """Test initialization with a pandas DataFrame."""
        ts = Timeseries(sample_pandas_df)
        assert isinstance(ts.get_timeseries(), pl.DataFrame)
        assert len(ts) == 4
        assert "time" in ts.get_timeseries().columns

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
        assert isinstance(ts.get_timeseries(), pl.DataFrame)
        assert len(ts) == 2
        assert "time" in ts.get_timeseries().columns

    def test_init_with_timeseries(self, sample_ts):
        """Test initialization with another Timeseries object."""
        ts = Timeseries(sample_ts)
        assert isinstance(ts.get_timeseries(), pl.DataFrame)
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


class TestTimeseriesBasicOperations:
    """Test basic operations of the Timeseries class."""

    def test_eq(self, sample_ts):
        """Test equality comparison."""
        ts1 = sample_ts
        ts2 = Timeseries(sample_ts.get_timeseries())
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

    def test_mul(self, sample_ts):
        """Test multiplication operation."""
        ts = sample_ts * 2
        assert isinstance(ts, Timeseries)

        # Original values should be doubled
        original_values = sample_ts.get_timeseries().select(pl.col("value1")).to_series()
        new_values = ts.get_timeseries().select(pl.col("value1")).to_series()

        for i, (orig, new) in enumerate(zip(original_values, new_values, strict=False)):
            assert new == orig * 2


class TestTimeseriesManipulation:
    """Test time series manipulation methods."""

    def test_remove_na(self, sample_df_with_nulls):
        """Test removal of null values."""
        ts = Timeseries(sample_df_with_nulls)
        assert len(ts) == 4

        ts_cleaned = ts.remove_na(inplace=False)
        assert len(ts_cleaned) == 2  # Only rows with no nulls remain
        assert len(ts) == 4  # Original unchanged

        ts.remove_na(inplace=True)
        assert len(ts) == 2  # Now original is changed

    def test_upsample_linear(self, sample_ts):
        """Test upsampling with linear interpolation."""
        original_len = len(sample_ts)
        upsampled = sample_ts.upsample("30m", inplace=False, strategy="linear")

        # Should have more rows now
        assert len(upsampled) > original_len

        # Check if upsampled correctly
        time_diffs = [
            (t2 - t1).total_seconds() / 60
            for t1, t2 in zip(
                upsampled.get_timeseries()["time"][:-1],
                upsampled.get_timeseries()["time"][1:],
                strict=False,
            )
        ]

        # All time differences should be 30 minutes
        assert all(diff == 30 for diff in time_diffs)

    def test_upsample_constant(self, sample_ts):
        """Test upsampling with constant fill."""
        upsampled = sample_ts.upsample("30m", inplace=False, strategy="constant")

        # Check if values are forward-filled
        times = upsampled.get_timeseries()["time"].to_list()
        values = upsampled.get_timeseries()["value1"].to_list()

        # For each original time point, check next 30-min point has same value
        for i in range(len(sample_ts) - 1):
            orig_time = sample_ts.get_timeseries()["time"][i]
            orig_value = sample_ts.get_timeseries()["value1"][i]

            # Find the next 30-min point in upsampled data
            next_time_idx = times.index(orig_time) + 1
            next_value = values[next_time_idx]

            assert next_value == orig_value  # Should be forward-filled

    def test_upsample_invalid_strategy(self, sample_ts):
        """Test upsampling with an invalid strategy."""
        with pytest.raises(NotImplementedError):
            sample_ts.upsample("30m", strategy="invalid")

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
        actual_means = grouped.get_timeseries()["value"].to_list()

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
        actual_sums = grouped.get_timeseries()["value"].to_list()

        assert actual_sums == expected_sums

    def test_groupby_with_invalid_agg(self, sample_ts):
        """Test grouping with an invalid aggregation function."""
        with pytest.raises(NotImplementedError):
            sample_ts.groupby("1h", agg="invalid")

    def test_select(self, sample_ts):
        """Test selecting specific variables."""
        # Original has time, value1, value2
        ts = sample_ts
        selected = ts.select(["time", "value1"], inplace=False)

        # Should only have time and value1 columns
        assert set(selected.get_timeseries().columns) == {"time", "value1"}
        assert "value2" not in selected.get_timeseries().columns

        # Original should be unchanged
        assert "value2" in ts.get_timeseries().columns

        # Test inplace
        ts.select(["time", "value1"], inplace=True)
        assert set(ts.get_timeseries().columns) == {"time", "value1"}

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
        joined = sample_ts.join(other_ts, by="time", how="inner", inplace=False)
        assert len(joined) == 3  # Only matching times
        assert set(joined.get_timeseries().columns) == {"time", "value1", "value2", "value3"}

        # Test left join
        left_joined = sample_ts.join(other_ts, by="time", how="left", inplace=False)
        assert len(left_joined) == 4  # All rows from sample_ts
        assert left_joined.get_timeseries()["value3"][3] is None  # Missing value for 3:00

        # Test inplace
        original_cols = sample_ts.get_timeseries().columns
        sample_ts.join(other_ts, inplace=True)
        assert set(sample_ts.get_timeseries().columns) != set(original_cols)
        assert "value3" in sample_ts.get_timeseries().columns

    def test_drop(self, sample_ts):
        """Test dropping columns."""
        # Original has time, value1, value2
        ts = sample_ts
        dropped = ts.drop(["value2"], inplace=False)

        # Should only have time and value1 columns
        assert set(dropped.get_timeseries().columns) == {"time", "value1"}
        assert "value2" not in dropped.get_timeseries().columns

        # Original should be unchanged
        assert "value2" in ts.get_timeseries().columns

        # Test inplace
        ts.drop(["value2"], inplace=True)
        assert set(ts.get_timeseries().columns) == {"time", "value1"}

    def test_get_granularity(self, sample_ts):
        """Test getting the time granularity."""
        # Sample has hourly data
        hourly = sample_ts.get_granularity(unit="hour")
        assert hourly == 1.0

        minute = sample_ts.get_granularity(unit="minute")
        assert minute == 60.0

        second = sample_ts.get_granularity(unit="second")
        assert second == 3600.0

    def test_get_granularity_invalid_unit(self, sample_ts):
        """Test getting granularity with an invalid unit."""
        with pytest.raises(ValueError):
            sample_ts.get_granularity(unit="invalid")

    def test_get_granularity_not_enough_points(self):
        """Test getting granularity with insufficient time points."""
        df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1, 0, 0, 0)],
                "value": [10.0],
            },
        )
        ts = Timeseries(df)
        with pytest.raises(ValueError):
            ts.get_granularity()

    def test_rename(self, sample_ts):
        """Test renaming columns."""
        ts = sample_ts
        renamed = ts.rename(["value1", "value2"], ["temperature", "pressure"], inplace=False)

        # Check new column names
        assert "temperature" in renamed.get_timeseries().columns
        assert "pressure" in renamed.get_timeseries().columns
        assert "value1" not in renamed.get_timeseries().columns
        assert "value2" not in renamed.get_timeseries().columns

        # Original should be unchanged
        assert "value1" in ts.get_timeseries().columns
        assert "value2" in ts.get_timeseries().columns

        # Test inplace
        ts.rename(["value1", "value2"], ["temperature", "pressure"], inplace=True)
        assert "temperature" in ts.get_timeseries().columns
        assert "pressure" in ts.get_timeseries().columns
        assert "value1" not in ts.get_timeseries().columns
        assert "value2" not in ts.get_timeseries().columns

    def test_timezone_operations(self, sample_ts):
        """Test timezone conversion operations."""
        ts = sample_ts
        assert ts.timezone == "UTC"

        # Change timezone
        ts.set_tz("America/New_York")
        assert ts.timezone == "America/New_York"

        # Verify times are converted
        times = ts.get_timeseries()["time"].to_list()
        for t in times:
            assert t.tzinfo is not None
            assert "America/New_York" in str(t.tzinfo)

    def test_invalid_timezone_conversion(self, sample_ts):
        """Test conversion to an invalid timezone."""
        with pytest.raises(ValueError):
            sample_ts.set_tz("Invalid/Timezone")


class TestTimeseriesExport:
    """Test exporting time series data."""

    def test_export_csv(self, sample_ts):
        """Test exporting to CSV format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.csv")
            sample_ts.export(path, file_format="csv")
            assert os.path.exists(path)

            # Check if file is readable
            df = pl.read_csv(path)
            assert len(df) == len(sample_ts)

    def test_export_parquet(self, sample_ts):
        """Test exporting to Parquet format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.parquet")
            sample_ts.export(path, file_format="parquet")
            assert os.path.exists(path)

            # Check if file is readable
            df = pl.read_parquet(path)
            assert len(df) == len(sample_ts)

    def test_export_pickle(self, sample_ts):
        """Test exporting to Pickle format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.pickle")
            sample_ts.export(path, file_format="pickle")
            assert os.path.exists(path)

            # Check if file is readable
            with open(path, "rb") as f:
                loaded_ts = pickle.load(f)
            assert isinstance(loaded_ts, Timeseries)
            assert len(loaded_ts) == len(sample_ts)

    def test_export_format_mismatch(self, sample_ts):
        """Test exporting with a format that doesn't match the file extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with pytest.raises(ValueError):
                sample_ts.export(path, file_format="csv")

    def test_export_unsupported_format(self, sample_ts):
        """Test exporting with an unsupported format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            with pytest.raises(NotImplementedError):
                sample_ts.export(path, file_format="json")
