import pandas as pd
import pendulum
import polars as pl
import pytest

from atlas.io.utils import get_metadata_from_file, get_metadata_from_frame


def test_get_metadata_from_frame_polars():
    df = pl.DataFrame(
        {
            "time": [pendulum.datetime(2025, 1, 1), pendulum.datetime(2025, 1, 2)],
            "category": ["A", "B"],
            "value": [1.0, 2.0],
        }
    )
    meta = get_metadata_from_frame(df)
    assert meta["shape"] == (2, 3)
    assert "datetime" in meta
    assert meta["datetime"]["column"] == "time"
    assert meta["datetime"]["min"] == "2025-01-01 00:00:00"
    assert meta["datetime"]["max"] == "2025-01-02 00:00:00"
    assert meta["datetime"]["nulls"] == 0
    assert "categorical" in meta
    assert meta["categorical"]["column"] == "category"
    assert meta["categorical"]["categories"] == ["A", "B"]
    assert meta["categorical"]["nulls"] == 0
    assert "numerical" in meta
    assert meta["numerical"]["column"] == "value"
    assert meta["numerical"]["min"] == 1.0
    assert meta["numerical"]["max"] == 2.0
    assert meta["numerical"]["nulls"] == 0


def test_get_metadata_from_frame_pandas():
    df = pd.DataFrame(
        {
            "time": [pendulum.datetime(2025, 1, 1), pendulum.datetime(2025, 1, 2)],
            "category": ["A", "B"],
            "value": [1.0, 2.0],
        }
    )
    meta = get_metadata_from_frame(df)
    assert meta["shape"] == (2, 3)
    assert meta["datetime"]["column"] == "time"
    assert meta["categorical"]["column"] == "category"
    assert meta["numerical"]["column"] == "value"


def test_get_metadata_from_frame_multiple_numeric():
    df = pl.DataFrame(
        {
            "time": [pendulum.datetime(2025, 1, 1), pendulum.datetime(2025, 1, 2)],
            "value1": [1.0, 2.0],
            "value2": [3.0, 4.0],
        }
    )
    meta = get_metadata_from_frame(df)
    assert "numericals" in meta
    assert set(meta["numericals"]) == {"value1", "value2"}


def test_get_metadata_from_frame_invalid():
    df = pl.DataFrame(
        {
            "time1": [pendulum.datetime(2025, 1, 1), pendulum.datetime(2025, 1, 2)],
            "time2": [pendulum.datetime(2025, 1, 3), pendulum.datetime(2025, 1, 4)],
            "value": [1.0, 2.0],
        }
    )
    with pytest.raises(ValueError):
        get_metadata_from_frame(df)


def test_get_metadata_from_file(tmp_path):
    # Create a temporary parquet file
    df = pl.DataFrame(
        {
            "time": [pendulum.datetime(2025, 1, 1), pendulum.datetime(2025, 1, 2)],
            "category": ["A", "B"],
            "value": [1.0, 2.0],
        }
    )
    file_path = tmp_path / "test.parquet"
    df.write_parquet(file_path)
    meta = get_metadata_from_file(file_path)
    assert meta["shape"] == (2, 3)
    assert meta["datetime"]["column"] == "time"
    assert meta["categorical"]["column"] == "category"
    assert meta["numerical"]["column"] == "value"
