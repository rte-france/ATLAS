from datetime import datetime

import pandas as pd
import pendulum
import polars as pl
import pytest
from pendulum import Timezone

from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries


@pytest.fixture
def sample_df():
    return pl.DataFrame(
        {
            "time": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
            "value": [1.0, 2.0],
        }
    )


@pytest.fixture
def sample_df_extended():
    return pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0),
                datetime(2023, 1, 1, 1, 0),
                datetime(2023, 1, 1, 2, 0),
                datetime(2023, 1, 1, 3, 0),
                datetime(2023, 1, 1, 4, 0),
                datetime(2023, 1, 1, 5, 0),
                datetime(2023, 1, 1, 6, 0),
                datetime(2023, 1, 1, 7, 0),
                datetime(2023, 1, 1, 8, 0),
                datetime(2023, 1, 1, 9, 0),
                datetime(2023, 1, 1, 10, 0),
                datetime(2023, 1, 1, 11, 0),
            ],
            "value": [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0],
        }
    )


@pytest.fixture
def sample_df_with_categories():
    return pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1),
                datetime(2023, 1, 2),
                datetime(2023, 1, 3),
                datetime(2023, 1, 4),
            ],
            "category": ["A", "A", "B", "B"],
            "value": [1.0, 2.0, 1.0, 2.0],
        }
    )


@pytest.fixture
def sample_df_invalid_schema():
    return pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1),
                datetime(2023, 1, 2),
                datetime(2023, 1, 3),
                datetime(2023, 1, 4),
            ],
            "time2": [
                datetime(2023, 1, 1),
                datetime(2023, 1, 2),
                datetime(2023, 1, 3),
                datetime(2023, 1, 4),
            ],
            "value": [1.0, 2.0, 1.0, 2.0],
        }
    )


@pytest.fixture
def sample_ts():
    return Timeseries(
        pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
                "value": [1.0, 2.0],
            }
        )
    )


def test_init_with_lazyframe(sample_df):
    lf = sample_df.lazy()
    lt = LazyTimeseries(lf)
    assert isinstance(lt.to_frame(), pl.LazyFrame)
    collected = lt.to_frame().collect()
    assert collected.shape == (2, 2)
    assert set(collected.columns) == {"time", "value"}


def test_init_with_none():
    lt = LazyTimeseries()
    assert isinstance(lt.to_frame(), pl.LazyFrame)
    collected = lt.to_frame().collect()
    assert collected.shape == (0, 2)
    assert set(collected.columns) == {"time", "value"}


def test_init_with_timeseries(sample_ts):
    lt = LazyTimeseries(sample_ts)
    assert lt.timezone == "UTC"
    df = lt.to_frame().collect()
    assert df.shape == (2, 2)


def test_init_with_lazy_timeseries(sample_df):
    lt1 = LazyTimeseries(sample_df.lazy(), timezone="UTC")
    lt2 = LazyTimeseries(lt1)
    assert isinstance(lt2.to_frame(), pl.LazyFrame)
    assert lt2.timezone == "UTC"


def test_invalid_timezone(sample_df):
    with pytest.raises(ValueError, match="Invalid timezone"):
        LazyTimeseries(sample_df.lazy(), timezone="Mars/Phobos")


def test_invalid_schema():
    bad_df = pl.DataFrame({"foo": [1, 2], "bar": [3, 4]}).lazy()
    with pytest.raises(ValueError, match="Timeseries must have exactly one numeric column"):
        LazyTimeseries(bad_df)


def test_from_file_parquet(tmp_path, sample_df):
    file_path = tmp_path / "data.parquet"
    sample_df.write_parquet(file_path)
    lt = LazyTimeseries.from_file(file_path)
    df = lt.to_frame().collect()
    assert df.shape == (2, 2)


def test_from_file_csv(tmp_path, sample_df):
    file_path = tmp_path / "data.csv"
    sample_df.write_csv(file_path, separator=";")
    lt = LazyTimeseries.from_file(file_path)
    df = lt.to_frame().collect()
    assert df.shape == (2, 2)


def test_from_str_input(tmp_path, sample_df):
    file_path = tmp_path / "data.parquet"
    sample_df.write_parquet(file_path)
    lt = LazyTimeseries.from_file(str(file_path))
    df = lt.to_frame().collect()
    assert df.shape == (2, 2)


def test_from_file_filter(tmp_path, sample_df_with_categories):
    file_path = tmp_path / "data.parquet"
    sample_df_with_categories.write_parquet(file_path)
    lt = LazyTimeseries.from_file(file_path, filters=("category", "A"))
    df = lt.to_frame().collect()
    assert df.shape == (2, 2)


def test_from_file_invalid_format(tmp_path):
    file_path = tmp_path / "data.txt"
    file_path.write_text("invalid")
    with pytest.raises(NotImplementedError, match="Atlas file should be a csv or parquet."):
        LazyTimeseries.from_file(file_path)


def test_init_invalid_type(sample_df_invalid_schema):
    with pytest.raises(ValueError, match="LazyTimeseries requires a LazyFrame or another Timeseries object"):
        LazyTimeseries(sample_df_invalid_schema)


def test_init_invalid_schema(sample_df_invalid_schema):
    with pytest.raises(ValueError, match="Timeseries must have exactly one datetime column"):
        LazyTimeseries(sample_df_invalid_schema.lazy())


def test_collect_returns_timeseries(sample_ts):
    lt = LazyTimeseries(sample_ts)
    collected = lt.collect()
    assert isinstance(collected, Timeseries) or hasattr(collected, "to_lazy")


def test_repr(sample_ts):
    lt = LazyTimeseries(sample_ts)
    repr_str = repr(lt)
    assert "LazyTimeseries with schema" in repr_str


def test_filter_single_datetime(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    target_date = datetime(2023, 1, 1, 3, 0)  # 03:00

    # Test inplace=True (default)
    filtered_lt = lt.filter(target_date)
    assert filtered_lt is lt  # Should return same instance
    collected = filtered_lt.collect()
    assert collected.timeseries.shape == (1, 2)
    assert collected.values == [25.0]


def test_filter_single_datetime_not_inplace(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    target_date = datetime(2023, 1, 1, 5, 0)  # 05:00

    # Test inplace=False
    filtered_lt = lt.filter(target_date, inplace=False)
    assert filtered_lt is not lt  # Should return new instance
    collected = filtered_lt.collect()
    assert collected.timeseries.shape == (1, 2)
    assert collected.values == [35.0]

    # Original should be unchanged
    original_collected = lt.collect()
    assert original_collected.timeseries.shape == (12, 2)


def test_filter_single_string(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    target_date_str = "2023-01-01 07:00:00"

    filtered_lt = lt.filter(target_date_str, inplace=False)
    collected = filtered_lt.collect()
    assert collected.timeseries.shape == (1, 2)
    assert collected.values == [45.0]


def test_filter_single_pendulum_datetime(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    target_date = pendulum.datetime(2023, 1, 1, 9, 0, tz="UTC")

    filtered_lt = lt.filter(target_date, inplace=False)
    collected = filtered_lt.collect()
    assert collected.timeseries.shape == (1, 2)
    assert collected.values == [55.0]


def test_filter_list_of_datetimes(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    target_dates = [datetime(2023, 1, 1, 2, 0), datetime(2023, 1, 1, 6, 0), datetime(2023, 1, 1, 10, 0)]

    filtered_lt = lt.filter(target_dates, inplace=False)
    collected = filtered_lt.collect()
    assert collected.timeseries.shape == (3, 2)
    assert sorted(collected.values) == [20.0, 40.0, 60.0]


def test_filter_custom_date_format(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    target_date_str = "2023/01/01 11:00"
    date_format = "YYYY/MM/DD HH:mm"

    filtered_lt = lt.filter(target_date_str, date_format=date_format, inplace=False)
    collected = filtered_lt.collect()
    assert collected.timeseries.shape == (1, 2)
    assert collected.values == [65.0]


def test_filter_no_matches(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    target_date = datetime(2023, 1, 1, 15, 0)  # 15:00 - not in hourly dataset

    filtered_lt = lt.filter(target_date, inplace=False)
    collected = filtered_lt.collect()
    assert collected.timeseries.shape == (0, 2)


def test_filter_invalid_type(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())

    with pytest.raises(TypeError):
        lt.filter(123)  # Invalid type


def test_filter_timezone_handling():
    # Test with different timezone
    df = pl.DataFrame(
        {
            "time": [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 1, 0)],
            "value": [100.0, 200.0],
        }
    )
    lt = LazyTimeseries(df.lazy(), timezone="Europe/Paris")
    target_date = datetime(2023, 1, 1, 0, 0)

    filtered_lt = lt.filter(target_date, inplace=False)
    collected = filtered_lt.collect()
    assert collected.timezone == "Europe/Paris"
    assert collected.timeseries.shape == (1, 2)


def test_set_frequency_inplace():
    df = pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0),
                datetime(2023, 1, 1, 2, 0),
                datetime(2023, 1, 1, 4, 0),
            ],
            "value": [10.0, 20.0, 30.0],
        }
    )
    lt = LazyTimeseries(df.lazy())

    result = lt.set_frequency("1h")

    # Should return same object when inplace=True
    assert result is lt

    collected = result.collect()
    assert collected.timeseries.shape[0] == 5  # 5 hourly points from 0h to 4h
    assert collected.values == [10.0, 10.0, 20.0, 20.0, 30.0]


def test_set_frequency_not_inplace():
    df = pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0),
                datetime(2023, 1, 1, 1, 0),
                datetime(2023, 1, 1, 2, 0),
                datetime(2023, 1, 1, 3, 0),
                datetime(2023, 1, 1, 4, 0),
                datetime(2023, 1, 1, 5, 0),
            ],
            "value": [10.0, 15.0, 20.0, 25.0, 30.0, 35.0],
        }
    )
    lt = LazyTimeseries(df.lazy())
    original_collected = lt.collect()

    result = lt.set_frequency("2h", inplace=False)

    assert result is not lt
    assert isinstance(result, LazyTimeseries)

    result_collected = result.collect()
    assert result_collected.timeseries.shape[0] == 3  # 3 two-hourly points

    current_collected = lt.collect()
    assert current_collected.timeseries.equals(original_collected.timeseries)


def test_set_frequency_with_pendulum_duration():
    # Test using pendulum.Duration instead of string
    df = pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0),
                datetime(2023, 1, 1, 6, 0),
                datetime(2023, 1, 1, 12, 0),
                datetime(2023, 1, 1, 18, 0),
            ],
            "value": [100.0, 200.0, 300.0, 400.0],
        }
    )
    lt = LazyTimeseries(df.lazy())

    duration = pendulum.duration(hours=3)
    result = lt.set_frequency(duration, inplace=False)

    collected = result.collect()
    assert collected.timeseries.shape[0] == 7


def test_set_frequency_same_frequency():
    df = pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0),
                datetime(2023, 1, 1, 1, 0),
                datetime(2023, 1, 1, 2, 0),
            ],
            "value": [10.0, 20.0, 30.0],
        }
    )
    lt = LazyTimeseries(df.lazy())
    original_collected = lt.collect()

    result = lt.set_frequency("1h", inplace=False)

    result_collected = result.collect()

    assert result_collected.timeseries.shape == original_collected.timeseries.shape
    assert result_collected.values == original_collected.values


def test_set_frequency_timezone_preservation():
    df = pl.DataFrame(
        {
            "time": [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 2, 0)],
            "value": [100.0, 200.0],
        }
    )
    lt = LazyTimeseries(df.lazy(), timezone="Europe/London")

    result = lt.set_frequency("1h", inplace=False)

    assert result.timezone == "Europe/London"
    collected = result.collect()
    assert collected.timezone == "Europe/London"


def test_abs_inplace():
    df = pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0),
                datetime(2023, 1, 1, 1, 0),
                datetime(2023, 1, 1, 2, 0),
                datetime(2023, 1, 1, 3, 0),
            ],
            "value": [-10.0, 15.0, -20.0, 25.0],
        }
    )
    lt = LazyTimeseries(df.lazy())

    result = lt.abs()

    # Should return same object when inplace=True (default)
    assert result is lt

    collected = result.collect()
    assert collected.values == [10.0, 15.0, 20.0, 25.0]


def test_abs_not_inplace():
    df = pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0),
                datetime(2023, 1, 1, 1, 0),
                datetime(2023, 1, 1, 2, 0),
            ],
            "value": [-5.0, -10.0, -15.0],
        }
    )
    lt = LazyTimeseries(df.lazy())
    original_collected = lt.collect()

    result = lt.abs(inplace=False)

    # Should return new object when inplace=False
    assert result is not lt
    assert isinstance(result, LazyTimeseries)

    result_collected = result.collect()
    assert result_collected.values == [5.0, 10.0, 15.0]

    # Original should be unchanged
    current_collected = lt.collect()
    assert current_collected.values == original_collected.values


def test_abs_timezone_preservation():
    df = pl.DataFrame(
        {
            "time": [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 1, 0)],
            "value": [-42.0, -13.7],
        }
    )
    lt = LazyTimeseries(df.lazy(), timezone="America/New_York")

    result = lt.abs(inplace=False)

    assert result.timezone == "America/New_York"
    collected = result.collect()
    assert collected.timezone == "America/New_York"
    assert collected.values == [42.0, 13.7]


def test_abs_empty_series():
    lt = LazyTimeseries()

    result = lt.abs(inplace=False)

    collected = result.collect()
    assert collected.timeseries.shape == (0, 2)
    assert result.timezone == "UTC"


def test_contains_with_datetime(sample_df_extended):
    """Test __contains__ with datetime object."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    dt_exists = datetime(2023, 1, 1, 3, 0)
    dt_not_exists = datetime(2023, 1, 1, 3, 30)

    assert dt_exists in lt
    assert dt_not_exists not in lt


def test_contains_with_string(sample_df_extended):
    """Test __contains__ with string datetime."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    dt_exists = "2023-01-01 05:00:00"
    dt_not_exists = "2023-01-01 15:00:00"

    assert dt_exists in lt
    assert dt_not_exists not in lt


def test_contains_with_pendulum_datetime(sample_df_extended):
    """Test __contains__ with pendulum.DateTime object."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    dt_exists = pendulum.datetime(2023, 1, 1, 7, 0, tz="UTC")
    dt_not_exists = pendulum.datetime(2023, 1, 1, 20, 0, tz="UTC")

    assert dt_exists in lt
    assert dt_not_exists not in lt


def test_contains_with_different_timezone():
    """Test __contains__ with datetime in different timezone."""
    df = pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0),
                datetime(2023, 1, 1, 1, 0),
                datetime(2023, 1, 1, 2, 0),
            ],
            "value": [10.0, 20.0, 30.0],
        }
    )
    lt = LazyTimeseries(df.lazy(), timezone="Europe/Paris")

    # Test with UTC datetime that corresponds to a time in the series
    # 2023-01-01 00:00:00 UTC = 2023-01-01 01:00:00 Europe/Paris
    dt_utc = pendulum.datetime(2023, 1, 1, 0, 0, tz="UTC")

    # The __contains__ should convert to the timeseries timezone
    assert dt_utc in lt


def test_contains_with_invalid_input(sample_df_extended):
    """Test __contains__ with invalid input returns False."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Invalid inputs should return False instead of raising an exception
    assert (123 in lt) is False
    assert (None in lt) is False
    assert ([] in lt) is False


def test_contains_empty_lazy_timeseries():
    """Test __contains__ on an empty LazyTimeseries."""
    lt = LazyTimeseries()

    dt = datetime(2023, 1, 1, 0, 0)
    assert dt not in lt


def test_max_with_values(sample_df_extended):
    """Test max() returns the maximum value."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Get max using lazy method
    max_val = lt.max()

    # Verify it matches the eager implementation
    eager_max = sample_df_extended["value"].max()
    assert max_val == eager_max


def test_min_with_values(sample_df_extended):
    """Test min() returns the minimum value."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Get min using lazy method
    min_val = lt.min()

    # Verify it matches the eager implementation
    eager_min = sample_df_extended["value"].min()
    assert min_val == eager_min


def test_sum_with_values(sample_df_extended):
    """Test sum() returns the sum of all values."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Get sum using lazy method
    sum_val = lt.sum()

    # Verify it matches the eager implementation
    eager_sum = sample_df_extended["value"].sum()
    assert sum_val == eager_sum


def test_max_empty_timeseries():
    """Test max() raises RuntimeError on empty timeseries."""
    lt = LazyTimeseries()

    with pytest.raises(RuntimeError, match="(?i)empty"):
        lt.max()


def test_min_empty_timeseries():
    """Test min() raises RuntimeError on empty timeseries."""
    lt = LazyTimeseries()

    with pytest.raises(RuntimeError, match="(?i)empty"):
        lt.min()


def test_sum_empty_timeseries():
    """Test sum() returns 0.0 for empty timeseries."""
    lt = LazyTimeseries()

    # Sum of empty series is 0.0
    assert lt.sum() == 0.0


# Tests for __len__


def test_len_with_values(sample_df_extended):
    """Test __len__() returns the correct number of rows."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Get length using lazy method
    length = len(lt)

    # Verify it matches the dataframe height
    assert length == sample_df_extended.height


def test_len_empty_timeseries():
    """Test __len__() returns 0 for empty timeseries."""
    lt = LazyTimeseries()

    assert len(lt) == 0


def test_get_by_index(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())

    assert lt.get_by_index(0) == 10.0
    assert lt.get_by_index(-1) == 65.0
    assert lt.get_by_index(3) == 25.0
    with pytest.raises(IndexError):
        lt.get_by_index(99)
    with pytest.raises(IndexError):
        lt.get_by_index(-99)
    with pytest.raises(IndexError):
        LazyTimeseries().get_by_index(0)


def test_get_time_by_index(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())

    expected_first = pendulum.instance(sample_df_extended.select("time").head(1).item())
    expected_last = pendulum.instance(sample_df_extended.select("time").tail(1).item())

    assert lt.get_time_by_index(0).to_datetime_string() == expected_first.to_datetime_string()
    assert lt.get_time_by_index(-1).to_datetime_string() == expected_last.to_datetime_string()
    with pytest.raises(IndexError):
        lt.get_time_by_index(99)
    with pytest.raises(IndexError):
        lt.get_time_by_index(-99)
    with pytest.raises(IndexError):
        LazyTimeseries().get_time_by_index(0)


def test_get_time_by_index_after_filter(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    dates = [datetime(2023, 1, 1, 1, 0), datetime(2023, 1, 1, 2, 0), datetime(2023, 1, 1, 3, 0)]
    lt.filter(dates, inplace=True)

    first = lt.get_time_by_index(0)
    last = lt.get_time_by_index(-1)

    assert first is not None and last is not None
    assert first <= last
    assert first.to_datetime_string() == "2023-01-01 01:00:00"
    assert last.to_datetime_string() == "2023-01-01 03:00:00"


# Tests for get_value


def test_get_value_with_datetime(sample_df_extended):
    """Test get_value() with datetime object."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Get a value that exists
    dt = datetime(2023, 1, 1, 1, 0)
    value = lt.get_value(dt)

    # Verify it matches the dataframe
    expected_value = sample_df_extended.filter(pl.col("time") == dt)["value"].item()
    assert value == expected_value


def test_get_value_with_string(sample_df_extended):
    """Test get_value() with string datetime."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Get a value that exists
    value = lt.get_value("2023-01-01 01:00:00")

    # Verify it matches the dataframe
    dt = datetime(2023, 1, 1, 1, 0)
    expected_value = sample_df_extended.filter(pl.col("time") == dt)["value"].item()
    assert value == expected_value


def test_get_value_with_pendulum_datetime(sample_df_extended):
    """Test get_value() with pendulum datetime."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Get a value that exists
    dt = pendulum.parse("2023-01-01 01:00:00", tz="UTC")
    value = lt.get_value(dt)

    # Verify it matches the dataframe
    expected_value = sample_df_extended.filter(pl.col("time") == datetime(2023, 1, 1, 1, 0))["value"].item()
    assert value == expected_value


def test_get_value_not_found(sample_df_extended):
    """Test get_value() raises KeyError when datetime not found."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Try to get a value that doesn't exist
    dt = datetime(2099, 1, 1, 0, 0)

    with pytest.raises(KeyError, match="not found"):
        lt.get_value(dt)


def test_get_value_empty_timeseries():
    """Test get_value() raises ValueError on empty timeseries."""
    lt = LazyTimeseries()

    with pytest.raises(ValueError, match="(?i)empty"):
        lt.get_value(datetime(2023, 1, 1, 0, 0))


def test_get_value_custom_date_format(sample_df_extended):
    """Test get_value() with custom date format."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Get a value with custom format
    value = lt.get_value("2023-01-01 01:00", date_format="YYYY-MM-DD HH:mm")

    # Verify it matches the dataframe
    dt = datetime(2023, 1, 1, 1, 0)
    expected_value = sample_df_extended.filter(pl.col("time") == dt)["value"].item()
    assert value == expected_value


def test_get_value_timezone_handling(sample_df_extended):
    """Test get_value() handles timezones correctly."""
    # Create LazyTimeseries with Europe/Paris timezone
    lt = LazyTimeseries(sample_df_extended.lazy(), timezone="Europe/Paris")

    # Get the first time in the series
    first_time = lt.get_time_by_index(0)
    if first_time:
        value = lt.get_value(first_time)
        assert isinstance(value, float)


def test_iter_rows(sample_df_extended):
    """Test iterating over rows of the LazyTimeseries."""

    lt = LazyTimeseries(sample_df_extended.lazy())
    rows = list(lt.iter_rows())

    # Check that we get the correct number of rows
    assert len(rows) == 12

    # Check that each row is a tuple of (time, value)
    assert all(isinstance(row, tuple) and len(row) == 2 for row in rows)

    # Check the first row
    assert rows[0][0] == datetime(2023, 1, 1, 0, 0, tzinfo=Timezone("UTC"))
    assert rows[0][1] == 10.0

    # Check the last row
    assert rows[-1][0] == datetime(2023, 1, 1, 11, 0, tzinfo=Timezone("UTC"))
    assert rows[-1][1] == 65.0

    # Check all values
    expected_values = [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0]
    actual_values = [row[1] for row in rows]
    assert actual_values == expected_values

    # Test that iter_rows returns an iterable
    rows_iterator = lt.iter_rows()
    first_row = next(rows_iterator)
    assert first_row == (datetime(2023, 1, 1, 0, 0, tzinfo=Timezone("UTC")), 10.0)


def test_iter_rows_empty():
    """Test iter_rows on an empty LazyTimeseries."""
    lt = LazyTimeseries()
    rows = list(lt.iter_rows())
    assert len(rows) == 0


def test_round():
    ts = LazyTimeseries(
        pl.DataFrame(
            {
                "time": [
                    datetime(2025, 12, 15, 0, 0, 0),
                    datetime(2025, 12, 15, 1, 0, 0),
                    datetime(2025, 12, 15, 2, 0, 0),
                    datetime(2025, 12, 15, 3, 0, 0),
                    datetime(2025, 12, 15, 4, 0, 0),
                ],
                "value": [1.12345, 2.0009, 3.9999, 4.0001, 5.29],
            },
        ).lazy()
    )

    ts.round(3)

    assert ts.get_value(datetime(2025, 12, 15, 0, 0, 0)) == 1.123
    assert ts.get_value(datetime(2025, 12, 15, 1, 0, 0)) == 2.001
    assert ts.get_value(datetime(2025, 12, 15, 2, 0, 0)) == 4
    assert ts.get_value(datetime(2025, 12, 15, 3, 0, 0)) == 4
    assert ts.get_value(datetime(2025, 12, 15, 4, 0, 0)) == 5.29


@pytest.fixture
def sample_lazy_ts():
    df = pd.DataFrame(
        {
            "time": pd.date_range(start="2023-01-01", periods=5, freq="h", tz="UTC"),
            "value": [10.0, 15.0, 20.0, 25.0, 30.0],
        }
    )
    return LazyTimeseries(pl.from_pandas(df).lazy())


@pytest.fixture
def another_lazy_ts():
    df = pd.DataFrame(
        {
            "time": pd.date_range(start="2023-01-01", periods=5, freq="h", tz="UTC"),
            "value": [2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )
    return LazyTimeseries(pl.from_pandas(df).lazy())


class TestLazyTimeseriesProperties:
    """Test LazyTimeseries properties that require collection."""

    def test_dataframe_property(self, sample_lazy_ts):
        """Test that .dataframe property returns LazyFrame."""
        df = sample_lazy_ts.dataframe
        assert isinstance(df, pl.LazyFrame)
        # Collect to verify it's the same data
        collected = df.collect()
        assert "time" in collected.columns
        assert "value" in collected.columns

    def test_lazyframe_property(self, sample_lazy_ts):
        """Test that .lazyframe property returns LazyFrame."""
        lf = sample_lazy_ts.lazyframe
        assert isinstance(lf, pl.LazyFrame)
        collected = lf.collect()
        assert collected.shape[0] == 5

    def test_index_property(self, sample_lazy_ts):
        """Test that .index property returns list of datetimes."""
        index = sample_lazy_ts.index
        assert isinstance(index, list)
        assert len(index) == 5
        assert all(isinstance(dt, datetime) for dt in index)

    def test_values_property(self, sample_lazy_ts):
        """Test that .values property returns list of floats."""
        values = sample_lazy_ts.values
        assert isinstance(values, list)
        assert len(values) == 5
        assert values == [10.0, 15.0, 20.0, 25.0, 30.0]

    def test_timestep_property(self, sample_lazy_ts):
        """Test that .timestep property returns Duration."""
        timestep = sample_lazy_ts.timestep
        assert isinstance(timestep, pendulum.Duration)
        assert timestep == pendulum.duration(hours=1)

    def test_metadata_property(self, sample_lazy_ts):
        """Test that .metadata property returns dict."""
        metadata = sample_lazy_ts.metadata
        assert isinstance(metadata, dict)
        # metadata comes from describe() which returns different keys
        assert "shape" in metadata
        assert "datetime" in metadata or "numerical" in metadata


class TestLazyTimeseriesArithmetic:
    """Test arithmetic operations on LazyTimeseries."""

    def test_mul_with_scalar(self, sample_lazy_ts):
        """Test multiplication with scalar value."""
        result = sample_lazy_ts * 2.0
        collected = result.collect()
        assert collected.values == [20.0, 30.0, 40.0, 50.0, 60.0]

    def test_mul_with_timeseries(self, sample_lazy_ts, another_lazy_ts):
        """Test multiplication with another LazyTimeseries."""
        result = sample_lazy_ts * another_lazy_ts
        collected = result.collect()
        expected = [10.0 * 2.0, 15.0 * 3.0, 20.0 * 4.0, 25.0 * 5.0, 30.0 * 6.0]
        assert collected.values == expected

    def test_add_with_scalar(self, sample_lazy_ts):
        """Test addition with scalar value."""
        result = sample_lazy_ts + 5.0
        collected = result.collect()
        assert collected.values == [15.0, 20.0, 25.0, 30.0, 35.0]

    def test_add_with_timeseries(self, sample_lazy_ts, another_lazy_ts):
        """Test addition with another LazyTimeseries."""
        result = sample_lazy_ts + another_lazy_ts
        collected = result.collect()
        expected = [10.0 + 2.0, 15.0 + 3.0, 20.0 + 4.0, 25.0 + 5.0, 30.0 + 6.0]
        assert collected.values == expected

    def test_sub_with_scalar(self, sample_lazy_ts):
        """Test subtraction with scalar value."""
        result = sample_lazy_ts - 5.0
        collected = result.collect()
        assert collected.values == [5.0, 10.0, 15.0, 20.0, 25.0]

    def test_sub_with_timeseries(self, sample_lazy_ts, another_lazy_ts):
        """Test subtraction with another LazyTimeseries."""
        result = sample_lazy_ts - another_lazy_ts
        collected = result.collect()
        expected = [10.0 - 2.0, 15.0 - 3.0, 20.0 - 4.0, 25.0 - 5.0, 30.0 - 6.0]
        assert collected.values == expected

    def test_neg_returns_lazy_timeseries(self, sample_lazy_ts):
        """__neg__ returns a LazyTimeseries instance."""
        result = -sample_lazy_ts
        assert isinstance(result, LazyTimeseries)

    def test_neg_negates_values(self, sample_lazy_ts):
        """__neg__ negates all values."""
        result = -sample_lazy_ts
        assert result.collect().values == [-10.0, -15.0, -20.0, -25.0, -30.0]

    def test_neg_preserves_index(self, sample_lazy_ts):
        """__neg__ preserves the time index."""
        result = -sample_lazy_ts
        assert result.index == sample_lazy_ts.index

    def test_neg_preserves_timezone(self, sample_lazy_ts):
        """__neg__ preserves the timezone."""
        result = -sample_lazy_ts
        assert result.timezone == sample_lazy_ts.timezone

    def test_neg_double_negation(self, sample_lazy_ts):
        """Applying __neg__ twice returns the original values."""
        result = -(-sample_lazy_ts)
        assert result.collect().values == sample_lazy_ts.collect().values

    def test_neg_does_not_modify_original(self, sample_lazy_ts):
        """__neg__ does not modify the original LazyTimeseries."""
        original_values = sample_lazy_ts.values[:]
        _ = -sample_lazy_ts
        assert sample_lazy_ts.values == original_values

    def test_neg_used_in_subtraction(self, sample_lazy_ts):
        """__neg__ allows use in expressions like -ts - other."""
        other = LazyTimeseries(
            pl.DataFrame(
                {
                    "time": [
                        datetime(2023, 1, 1, 0, 0),
                        datetime(2023, 1, 1, 1, 0),
                        datetime(2023, 1, 1, 2, 0),
                        datetime(2023, 1, 1, 3, 0),
                        datetime(2023, 1, 1, 4, 0),
                    ],
                    "value": [1.0, -2.0, 3.0, -44.0, 0],
                }
            ).lazy()
        )
        result = -sample_lazy_ts - other
        assert result.collect().values == [-11.0, -13.0, -23.0, 19, -30]

    def test_div_with_scalar(self, sample_lazy_ts):
        """Test division with scalar value."""
        result = sample_lazy_ts / 2.0
        collected = result.collect()
        assert collected.values == [5.0, 7.5, 10.0, 12.5, 15.0]

    def test_div_with_timeseries(self, sample_lazy_ts, another_lazy_ts):
        """Test division with another LazyTimeseries."""
        result = sample_lazy_ts / another_lazy_ts
        collected = result.collect()
        expected = [10.0 / 2.0, 15.0 / 3.0, 20.0 / 4.0, 25.0 / 5.0, 30.0 / 6.0]
        assert collected.values == expected


class TestLazyTimeseriesModification:
    """Test modification methods that delegate to eager version."""

    def test_set_value(self, sample_lazy_ts):
        """Test set_value method."""
        first_time = sample_lazy_ts.index[0]
        result = sample_lazy_ts.set_value(first_time, 999.0, inplace=False)
        collected = result.collect()
        assert collected.timeseries["value"][0] == 999.0

    def test_mul_value_at(self, sample_lazy_ts):
        """Test mul_value_at method."""
        first_time = sample_lazy_ts.index[0]
        result = sample_lazy_ts.mul_value_at(first_time, 2.0, inplace=False)
        collected = result.collect()
        assert collected.timeseries["value"][0] == 20.0  # 10.0 * 2.0


class TestLazyTimeseriesAdvanced:
    """Test advanced methods like groupby."""

    def test_groupby(self, sample_lazy_ts):
        """Test groupby method."""
        result = sample_lazy_ts.groupby("1d", agg="sum", inplace=False)
        collected = result.collect()
        # Should aggregate all hourly values into one daily value
        assert collected.timeseries.shape[0] == 1


class TestLazyTimeseriesIO:
    """Test I/O methods."""

    def test_to_file_csv(self, sample_lazy_ts, tmp_path):
        """Test to_file method with CSV."""
        file_path = tmp_path / "test_lazy.csv"
        sample_lazy_ts.to_file(file_path, file_format="csv")
        assert file_path.exists()

        # Load and verify
        loaded = LazyTimeseries.from_file(file_path, timezone="UTC")
        collected_original = sample_lazy_ts.collect()
        collected_loaded = loaded.collect()
        assert collected_original.timeseries.shape == collected_loaded.timeseries.shape

    def test_to_file_parquet(self, sample_lazy_ts, tmp_path):
        """Test to_file method with Parquet."""
        file_path = tmp_path / "test_lazy.parquet"
        sample_lazy_ts.to_file(file_path, file_format="parquet")
        assert file_path.exists()


class TestLazyTimeseriesVisualization:
    """Test visualization methods."""

    def test_plot(self, sample_lazy_ts):
        """Test plot method returns a plotly figure."""
        fig = sample_lazy_ts.plot(title="Test Plot")
        # Check that it returns a plotly figure
        assert hasattr(fig, "data")
        assert hasattr(fig, "layout")
        assert fig.layout.title.text == "Test Plot"


class TestLazyTimeseriesSlicing:
    """Test slicing operations."""

    def test_slice_with_datetimes(self, sample_lazy_ts):
        """Test slice method with datetime range."""
        index = sample_lazy_ts.index
        # slice takes start_bound and end_bound as arguments
        result = sample_lazy_ts.slice(index[1], index[3], inplace=False)
        collected = result.collect()
        assert collected.timeseries.shape[0] == 3  # Includes start and end


class TestLazyTimeseriesDescribe:
    """Test describe method."""

    def test_describe(self, sample_lazy_ts):
        """Test describe method returns metadata."""
        description = sample_lazy_ts.describe()
        assert isinstance(description, dict)
        # describe() returns shape, datetime info, numerical info
        assert "shape" in description
        assert description["shape"] == (5, 2)


class TestFromValues:
    """Tests for LazyTimeseries.from_values classmethod."""

    def test_from_values_basic(self):
        """Create a LazyTimeseries from start date, frequency and values list."""
        lt = LazyTimeseries.from_values(
            start_date="2023-01-01 00:00:00",
            frequency="1h",
            values=[10.0, 20.0, 30.0],
        )
        assert isinstance(lt, LazyTimeseries)
        assert len(lt) == 3
        assert lt.values == [10.0, 20.0, 30.0]

    def test_from_values_timezone(self):
        """from_values respects the given timezone."""
        lt = LazyTimeseries.from_values(
            start_date="2023-01-01 00:00:00",
            frequency="1h",
            values=[1.0, 2.0],
            timezone="Europe/Paris",
        )
        assert lt.timezone == "Europe/Paris"

    def test_from_values_pendulum_start(self):
        """from_values accepts a pendulum.DateTime as start_date."""
        start = pendulum.datetime(2023, 6, 1, 12, 0, tz="UTC")
        lt = LazyTimeseries.from_values(
            start_date=start,
            frequency="30m",
            values=[5.0, 10.0, 15.0],
        )
        assert len(lt) == 3
        assert lt.get_time_by_index(0) == start

    def test_from_values_too_few_values(self):
        """from_values raises ValueError when fewer than 2 values are provided."""
        with pytest.raises(ValueError, match="at least 2 values"):
            LazyTimeseries.from_values(
                start_date="2023-01-01 00:00:00",
                frequency="1h",
                values=[42.0],
            )

    def test_from_values_correct_timestamps(self):
        """from_values generates the correct timestamps based on frequency."""
        lt = LazyTimeseries.from_values(
            start_date="2023-01-01 00:00:00",
            frequency="1h",
            values=[1.0, 2.0, 3.0, 4.0],
        )
        index = lt.index
        assert len(index) == 4
        # Check step is 1 hour
        assert lt.timestep == pendulum.duration(hours=1)


class TestFromIndex:
    """Tests for LazyTimeseries.from_index classmethod."""

    def test_from_index_scalar_default(self):
        """from_index with scalar default_value fills every timestamp with that value."""
        lt = LazyTimeseries.from_index(
            start_date="2023-01-01 00:00:00",
            frequency="1h",
            end_date="2023-01-01 03:00:00",
            default_value=0.0,
        )
        assert isinstance(lt, LazyTimeseries)
        assert len(lt) == 4
        assert all(v == 0.0 for v in lt.values)

    def test_from_index_list_default(self):
        """from_index with a list default_value uses the provided values."""
        values = [1.0, 2.0, 3.0, 4.0]
        lt = LazyTimeseries.from_index(
            start_date="2023-01-01 00:00:00",
            frequency="1h",
            end_date="2023-01-01 03:00:00",
            default_value=values,
        )
        assert lt.values == values

    def test_from_index_list_wrong_size(self):
        """from_index raises ValueError when list size doesn't match generated timestamps."""
        with pytest.raises(ValueError, match="size"):
            LazyTimeseries.from_index(
                start_date="2023-01-01 00:00:00",
                frequency="1h",
                end_date="2023-01-01 03:00:00",
                default_value=[1.0, 2.0],  # only 2 values but 4 timestamps
            )

    def test_from_index_timezone(self):
        """from_index respects the given timezone."""
        lt = LazyTimeseries.from_index(
            start_date="2023-01-01 00:00:00",
            frequency="1h",
            end_date="2023-01-01 02:00:00",
            timezone="America/New_York",
        )
        assert lt.timezone == "America/New_York"

    def test_from_index_integer_default(self):
        """from_index accepts an int as default_value."""
        lt = LazyTimeseries.from_index(
            start_date="2023-01-01 00:00:00",
            frequency="1h",
            end_date="2023-01-01 01:00:00",
            default_value=7,
        )
        assert lt.values == [7.0, 7.0]

    def test_from_index_correct_bounds(self):
        """from_index generates timestamps from start to end inclusive."""
        lt = LazyTimeseries.from_index(
            start_date="2023-03-01 00:00:00",
            frequency="1d",
            end_date="2023-03-05 00:00:00",
        )
        assert len(lt) == 5
        assert lt.get_time_by_index(0).date() == pendulum.date(2023, 3, 1)
        assert lt.get_time_by_index(-1).date() == pendulum.date(2023, 3, 5)


class TestFromTimeseries:
    """Tests for LazyTimeseries.from_timeseries classmethod."""

    def test_from_lazy_timeseries(self, sample_lazy_ts):
        """from_timeseries with a LazyTimeseries copies the data."""
        lt = LazyTimeseries.from_timeseries(sample_lazy_ts)
        assert isinstance(lt, LazyTimeseries)
        assert lt.values == sample_lazy_ts.values

    def test_from_lazy_timeseries_with_default_value(self, sample_lazy_ts):
        """from_timeseries with default_value overrides all values."""
        lt = LazyTimeseries.from_timeseries(sample_lazy_ts, default_value=99.0)
        assert all(v == 99.0 for v in lt.values)
        # Structure (index) is preserved
        assert lt.index == sample_lazy_ts.index

    def test_from_timeseries_eager(self, sample_ts):
        """from_timeseries with an eager Timeseries wraps it lazily."""
        lt = LazyTimeseries.from_timeseries(sample_ts)
        assert isinstance(lt, LazyTimeseries)
        assert lt.values == sample_ts.values

    def test_from_timeseries_eager_with_default_value(self, sample_ts):
        """from_timeseries with Timeseries and default_value overrides values."""
        lt = LazyTimeseries.from_timeseries(sample_ts, default_value=0.0)
        assert all(v == 0.0 for v in lt.values)

    def test_from_timeseries_invalid_type(self):
        """from_timeseries raises TypeError for non-timeseries input."""
        with pytest.raises(TypeError, match="timeseries"):
            LazyTimeseries.from_timeseries({"not": "a timeseries"})

    def test_from_timeseries_preserves_timezone(self):
        """from_timeseries preserves the timezone of the source timeseries."""
        df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 1, 0)],
                "value": [1.0, 2.0],
            }
        )
        source = LazyTimeseries(df.lazy(), timezone="Europe/Paris")
        lt = LazyTimeseries.from_timeseries(source)
        assert lt.timezone == "Europe/Paris"


class TestFromDataframe:
    """Tests for LazyTimeseries.from_dataframe classmethod."""

    def test_from_polars_dataframe(self, sample_df):
        """from_dataframe wraps a pl.DataFrame."""
        lt = LazyTimeseries.from_dataframe(sample_df)
        assert isinstance(lt, LazyTimeseries)
        assert len(lt) == 2

    def test_from_polars_lazyframe(self, sample_df):
        """from_dataframe wraps a pl.LazyFrame."""
        lt = LazyTimeseries.from_dataframe(sample_df.lazy())
        assert isinstance(lt, LazyTimeseries)
        assert len(lt) == 2

    def test_from_pandas_dataframe(self):
        """from_dataframe wraps a pd.DataFrame."""
        df = pd.DataFrame(
            {
                "time": pd.date_range("2023-01-01", periods=3, freq="h"),
                "value": [1.0, 2.0, 3.0],
            }
        )
        lt = LazyTimeseries.from_dataframe(df, timezone="UTC")
        assert isinstance(lt, LazyTimeseries)
        assert len(lt) == 3
        assert lt.values == [1.0, 2.0, 3.0]

    def test_from_dataframe_timezone(self, sample_df):
        """from_dataframe respects the given timezone."""
        lt = LazyTimeseries.from_dataframe(sample_df, timezone="Europe/London")
        assert lt.timezone == "Europe/London"

    def test_from_dataframe_invalid_type(self):
        """from_dataframe raises TypeError for unsupported input."""
        with pytest.raises(TypeError, match="dataframe"):
            LazyTimeseries.from_dataframe([1, 2, 3])


class TestGetShape:
    """Tests for LazyTimeseries._get_shape (exposed via .shape property)."""

    def test_shape_non_empty(self, sample_lazy_ts):
        """shape returns (n_rows, n_cols) for a non-empty LazyTimeseries."""
        shape = sample_lazy_ts.shape
        assert shape == (5, 2)

    def test_shape_empty(self):
        """shape returns (0, 2) for an empty LazyTimeseries."""
        lt = LazyTimeseries()
        assert lt.shape == (0, 2)

    def test_shape_after_filter(self, sample_df_extended):
        """shape reflects the row count after filtering."""
        lt = LazyTimeseries(sample_df_extended.lazy())
        filtered = lt.filter(
            [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 1, 0)],
            inplace=False,
        )
        assert filtered.shape == (2, 2)

    def test_shape_columns(self, sample_lazy_ts):
        """shape always reports 2 columns (time + value)."""
        assert sample_lazy_ts.shape[1] == 2


class TestAddIndex:
    """Tests for LazyTimeseries.add_index method."""

    def test_add_index_inplace(self, sample_lazy_ts):
        """add_index with inplace=True appends a new (time, value) row."""
        # sample_lazy_ts has hourly data from 00:00 to 04:00 UTC on 2023-01-01
        # append the next consecutive hour so the series stays regular
        original_len = len(sample_lazy_ts)
        new_time = datetime(2023, 1, 1, 5, 0)
        result = sample_lazy_ts.add_index(new_time, 99.0)
        assert result is sample_lazy_ts
        assert len(result) == original_len + 1
        assert result.get_value(new_time) == 99.0

    def test_add_index_not_inplace(self, sample_lazy_ts):
        """add_index with inplace=False returns a new LazyTimeseries."""
        # sample_lazy_ts has hourly data from 00:00 to 04:00 UTC on 2023-01-01
        original_len = len(sample_lazy_ts)
        new_time = datetime(2023, 1, 1, 5, 0)
        result = sample_lazy_ts.add_index(new_time, 42.0, inplace=False)
        assert result is not sample_lazy_ts
        assert isinstance(result, LazyTimeseries)
        assert len(result) == original_len + 1
        # Original is unchanged
        assert len(sample_lazy_ts) == original_len

    def test_add_index_string_datetime(self, sample_lazy_ts):
        """add_index accepts a string datetime."""
        # sample_lazy_ts has hourly data from 00:00 to 04:00 UTC on 2023-01-01
        original_len = len(sample_lazy_ts)
        result = sample_lazy_ts.add_index("2023-01-01 05:00:00", 77.0, inplace=False)
        assert len(result) == original_len + 1

    def test_add_index_value_correct(self):
        """add_index stores the correct value at the new timestamp."""
        df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 1, 0)],
                "value": [10.0, 20.0],
            }
        )
        lt = LazyTimeseries(df.lazy())
        new_time = datetime(2023, 1, 1, 2, 0)
        lt.add_index(new_time, 30.0)
        assert lt.get_value(new_time) == 30.0


class TestAddIndexes:
    """Tests for LazyTimeseries.add_indexes method."""

    def test_add_indexes_from_lazy_timeseries(self):
        """add_indexes appends rows from another LazyTimeseries."""
        base_df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 1, 0)],
                "value": [1.0, 2.0],
            }
        )
        extra_df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1, 2, 0), datetime(2023, 1, 1, 3, 0)],
                "value": [3.0, 4.0],
            }
        )
        base = LazyTimeseries(base_df.lazy())
        extra = LazyTimeseries(extra_df.lazy())
        result = base.add_indexes(extra, inplace=False)
        assert len(result) == 4
        assert result.values == [1.0, 2.0, 3.0, 4.0]

    def test_add_indexes_from_timeseries(self, sample_ts):
        """add_indexes accepts an eager Timeseries as input."""
        base_df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 3), datetime(2023, 1, 4)],
                "value": [99.0, 100.0],
            }
        )
        base = LazyTimeseries(base_df.lazy())
        result = base.add_indexes(sample_ts, inplace=False)
        # sample_ts has 2 rows, base has 2 rows → combined 4 rows
        assert len(result) == 4

    def test_add_indexes_inplace(self):
        """add_indexes with inplace=True modifies the object in place."""
        base_df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1, 0, 0)],
                "value": [1.0],
            }
        )
        extra_df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1, 1, 0)],
                "value": [2.0],
            }
        )
        base = LazyTimeseries(base_df.lazy())
        extra = LazyTimeseries(extra_df.lazy())
        result = base.add_indexes(extra)
        assert result is base
        assert len(base) == 2

    def test_add_indexes_not_inplace_original_unchanged(self):
        """add_indexes with inplace=False leaves the original intact."""
        base_df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1, 0, 0)],
                "value": [1.0],
            }
        )
        extra_df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1, 1, 0)],
                "value": [2.0],
            }
        )
        base = LazyTimeseries(base_df.lazy())
        extra = LazyTimeseries(extra_df.lazy())
        base.add_indexes(extra, inplace=False)
        assert len(base) == 1


class TestSetValues:
    """Tests for LazyTimeseries.set_values method."""

    def test_set_values_overwrites_existing(self, sample_lazy_ts):
        """set_values with an overlapping LazyTimeseries overwrites existing values."""
        override_df = pl.DataFrame(
            {
                "time": pd.date_range("2023-01-01", periods=5, freq="h", tz="UTC").to_list(),
                "value": [100.0, 200.0, 300.0, 400.0, 500.0],
            }
        )
        override = LazyTimeseries(override_df.lazy())
        result = sample_lazy_ts.set_values(override, inplace=False)
        assert result.values == [100.0, 200.0, 300.0, 400.0, 500.0]

    def test_set_values_inplace(self, sample_lazy_ts):
        """set_values with inplace=True modifies the object and returns self."""
        override_df = pl.DataFrame(
            {
                "time": pd.date_range("2023-01-01", periods=5, freq="h", tz="UTC").to_list(),
                "value": [0.0, 0.0, 0.0, 0.0, 0.0],
            }
        )
        override = LazyTimeseries(override_df.lazy())
        result = sample_lazy_ts.set_values(override)
        assert result is sample_lazy_ts
        assert all(v == 0.0 for v in sample_lazy_ts.values)

    def test_set_values_not_inplace_original_unchanged(self):
        """set_values with inplace=False leaves the original unchanged."""
        base_df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 1, 0)],
                "value": [1.0, 2.0],
            }
        )
        override_df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 1, 0)],
                "value": [99.0, 88.0],
            }
        )
        base = LazyTimeseries(base_df.lazy())
        override = LazyTimeseries(override_df.lazy())
        base.set_values(override, inplace=False)
        assert base.values == [1.0, 2.0]

    def test_set_values_from_eager_timeseries(self, sample_ts):
        """set_values accepts an eager Timeseries as input."""
        # sample_ts has values [1.0, 2.0] at 2023-01-01 and 2023-01-02
        base_df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
                "value": [10.0, 20.0],
            }
        )
        base = LazyTimeseries(base_df.lazy())
        override = Timeseries(
            pl.DataFrame(
                {
                    "time": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
                    "value": [55.0, 66.0],
                }
            )
        )
        result = base.set_values(override, inplace=False)
        assert result.values == [55.0, 66.0]
