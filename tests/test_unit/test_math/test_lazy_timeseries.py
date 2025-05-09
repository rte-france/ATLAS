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


def test_invalid_schema(sample_df):
    bad_df = pl.DataFrame({"foo": [1, 2], "bar": [3, 4]}).lazy()
    with pytest.raises(ValueError, match="Timeseries must have exactly one numeric column"):
        LazyTimeseries(bad_df)


def test_from_file_parquet(tmp_path, sample_df):
    file_path = tmp_path / "data.parquet"
    sample_df.write_parquet(file_path)
    lt = LazyTimeseries.from_file(file_path)
    df = lt.get_data().collect()
    assert df.shape == (2, 2)


def test_from_file_invalid_format(tmp_path):
    file_path = tmp_path / "data.txt"
    file_path.write_text("invalid")
    with pytest.raises(ValueError, match="Unsupported file format"):
        LazyTimeseries.from_file(file_path)


def test_collect_returns_timeseries(sample_ts):
    lt = LazyTimeseries(sample_ts)
    collected = lt.collect()
    assert isinstance(collected, Timeseries) or hasattr(collected, "to_lazy")
