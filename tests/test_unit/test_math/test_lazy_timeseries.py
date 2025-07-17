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

    with pytest.raises(NotImplementedError, match="Invalid filter formatting"):
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
