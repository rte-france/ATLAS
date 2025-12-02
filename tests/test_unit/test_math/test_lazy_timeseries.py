from datetime import datetime

import pendulum
import polars as pl
import pytest

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
    assert collected.timeseries["value"].to_list() == [25.0]


def test_filter_single_datetime_not_inplace(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    target_date = datetime(2023, 1, 1, 5, 0)  # 05:00

    # Test inplace=False
    filtered_lt = lt.filter(target_date, inplace=False)
    assert filtered_lt is not lt  # Should return new instance
    collected = filtered_lt.collect()
    assert collected.timeseries.shape == (1, 2)
    assert collected.timeseries["value"].to_list() == [35.0]

    # Original should be unchanged
    original_collected = lt.collect()
    assert original_collected.timeseries.shape == (12, 2)


def test_filter_single_string(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    target_date_str = "2023-01-01 07:00:00"

    filtered_lt = lt.filter(target_date_str, inplace=False)
    collected = filtered_lt.collect()
    assert collected.timeseries.shape == (1, 2)
    assert collected.timeseries["value"].to_list() == [45.0]


def test_filter_single_pendulum_datetime(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    target_date = pendulum.datetime(2023, 1, 1, 9, 0, tz="UTC")

    filtered_lt = lt.filter(target_date, inplace=False)
    collected = filtered_lt.collect()
    assert collected.timeseries.shape == (1, 2)
    assert collected.timeseries["value"].to_list() == [55.0]


def test_filter_list_of_datetimes(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    target_dates = [datetime(2023, 1, 1, 2, 0), datetime(2023, 1, 1, 6, 0), datetime(2023, 1, 1, 10, 0)]

    filtered_lt = lt.filter(target_dates, inplace=False)
    collected = filtered_lt.collect()
    assert collected.timeseries.shape == (3, 2)
    assert sorted(collected.timeseries["value"].to_list()) == [20.0, 40.0, 60.0]


def test_filter_custom_date_format(sample_df_extended):
    lt = LazyTimeseries(sample_df_extended.lazy())
    target_date_str = "2023/01/01 11:00"
    date_format = "YYYY/MM/DD HH:mm"

    filtered_lt = lt.filter(target_date_str, date_format=date_format, inplace=False)
    collected = filtered_lt.collect()
    assert collected.timeseries.shape == (1, 2)
    assert collected.timeseries["value"].to_list() == [65.0]


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
    assert collected.timeseries["value"].to_list() == [10.0, 10.0, 20.0, 20.0, 30.0]


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
    assert result_collected.timeseries["value"].to_list() == original_collected.timeseries["value"].to_list()


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
    assert collected.timeseries["value"].to_list() == [10.0, 15.0, 20.0, 25.0]


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
    assert result_collected.timeseries["value"].to_list() == [5.0, 10.0, 15.0]

    # Original should be unchanged
    current_collected = lt.collect()
    assert current_collected.timeseries["value"].to_list() == original_collected.timeseries["value"].to_list()


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
    assert collected.timeseries["value"].to_list() == [42.0, 13.7]


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


# Tests for aggregation methods (max, min, sum)


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


# Tests for first_date and last_date


def test_first_date_with_values(sample_df_extended):
    """Test first_date() returns the earliest date."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Get first date using lazy method
    first = lt.first_date()

    # Verify it matches the first row's time
    expected_first = sample_df_extended.select("time").head(1).item()
    assert first is not None
    assert first.to_datetime_string() == pendulum.instance(expected_first).to_datetime_string()


def test_last_date_with_values(sample_df_extended):
    """Test last_date() returns the latest date."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Get last date using lazy method
    last = lt.last_date()

    # Verify it matches the last row's time
    expected_last = sample_df_extended.select("time").tail(1).item()
    assert last is not None
    assert last.to_datetime_string() == pendulum.instance(expected_last).to_datetime_string()


def test_first_date_empty_timeseries():
    """Test first_date() returns None for empty timeseries."""
    lt = LazyTimeseries()

    assert lt.first_date() is None


def test_last_date_empty_timeseries():
    """Test last_date() returns None for empty timeseries."""
    lt = LazyTimeseries()

    assert lt.last_date() is None


def test_first_last_date_after_filter(sample_df_extended):
    """Test first_date() and last_date() work correctly after filtering."""
    lt = LazyTimeseries(sample_df_extended.lazy())

    # Filter to a subset
    dates = [datetime(2023, 1, 1, 1, 0), datetime(2023, 1, 1, 2, 0), datetime(2023, 1, 1, 3, 0)]
    lt.filter(dates, inplace=True)

    # Check first and last dates
    first = lt.first_date()
    last = lt.last_date()

    assert first is not None
    assert last is not None
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
    first_time = lt.first_date()
    if first_time:
        value = lt.get_value(first_time)
        assert isinstance(value, float)
