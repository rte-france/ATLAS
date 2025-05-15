from datetime import datetime

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
    assert isinstance(lt.get_data(), pl.LazyFrame)
    collected = lt.get_data().collect()
    assert collected.shape == (2, 2)
    assert set(collected.columns) == {"time", "value"}


def test_init_with_none():
    lt = LazyTimeseries()
    assert isinstance(lt.get_data(), pl.LazyFrame)
    collected = lt.get_data().collect()
    assert collected.shape == (0, 2)
    assert set(collected.columns) == {"time", "value"}


def test_init_with_timeseries(sample_ts):
    lt = LazyTimeseries(sample_ts)
    assert lt.timezone == "UTC"
    df = lt.get_data().collect()
    assert df.shape == (2, 2)


def test_init_with_lazy_timeseries(sample_df):
    lt1 = LazyTimeseries(sample_df.lazy(), timezone="UTC")
    lt2 = LazyTimeseries(lt1)
    assert isinstance(lt2.get_data(), pl.LazyFrame)
    assert lt2.timezone == "UTC"


def test_invalid_timezone(sample_df):
    with pytest.raises(ValueError, match="Invalid timezone"):
        LazyTimeseries(sample_df.lazy(), timezone="Mars/Phobos")


def test_invalid_interpolation_method(sample_df):
    with pytest.raises(NotImplementedError):
        LazyTimeseries(sample_df.lazy(), interpolation_method="spline")


def test_invalid_schema():
    bad_df = pl.DataFrame({"foo": [1, 2], "bar": [3, 4]}).lazy()
    with pytest.raises(ValueError, match="Timeseries must have exactly one numeric column"):
        LazyTimeseries(bad_df)


def test_from_file_parquet(tmp_path, sample_df):
    file_path = tmp_path / "data.parquet"
    sample_df.write_parquet(file_path)
    lt = LazyTimeseries.from_file(file_path)
    df = lt.get_data().collect()
    assert df.shape == (2, 2)


def test_from_file_csv(tmp_path, sample_df):
    file_path = tmp_path / "data.csv"
    sample_df.write_csv(file_path, separator=";")
    lt = LazyTimeseries.from_file(file_path)
    df = lt.get_data().collect()
    assert df.shape == (2, 2)


def test_from_str_input(tmp_path, sample_df):
    file_path = tmp_path / "data.parquet"
    sample_df.write_parquet(file_path)
    lt = LazyTimeseries.from_file(str(file_path))
    df = lt.get_data().collect()
    assert df.shape == (2, 2)


def test_from_file_filter(tmp_path, sample_df_with_categories):
    file_path = tmp_path / "data.parquet"
    sample_df_with_categories.write_parquet(file_path)
    lt = LazyTimeseries.from_file(file_path, filters=("category", "A"))
    df = lt.get_data().collect()
    assert df.shape == (2, 2)


def test_from_file_invalid_format(tmp_path):
    file_path = tmp_path / "data.txt"
    file_path.write_text("invalid")
    with pytest.raises(ValueError, match="Unsupported file format"):
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
