# test_matrix.py


import pandas as pd
import polars as pl
import pytest

from atlas.math.matrix import Matrix
from atlas.math.timeseries import Timeseries


@pytest.fixture
def sample_pandas_df():
    return pd.DataFrame(
        {
            "time": pd.date_range(start="2025-01-01", periods=4, freq="D"),
            "scenario1": [1, 2, 3, 4],
            "scenario2": [5, 6, 7, 8],
        }
    )


@pytest.fixture
def sample_polars_df(sample_pandas_df):
    return pl.from_pandas(sample_pandas_df)


def test_init_with_polars(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    assert matrix.indexes == ["scenario1", "scenario2"]
    assert matrix.matrix.shape == (4, 3)


def test_init_with_pandas(sample_pandas_df):
    matrix = Matrix(sample_pandas_df)
    assert matrix.indexes == ["scenario1", "scenario2"]
    assert matrix.matrix.shape == (4, 3)


def test_invalid_timezone(sample_polars_df):
    with pytest.raises(ValueError, match="Invalid timezone"):
        Matrix(sample_polars_df, timezone="Mars/Phobos")


def test_getitem(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    ts = matrix["scenario1"]
    assert ts.shape == (4, 2)  # time + scenario1


def test_getitem_invalid(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    with pytest.raises(KeyError, match="No timeseries found"):
        _ = matrix["non_existing"]


def test_contains(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    assert "scenario1" in matrix
    assert "non_existing" not in matrix


def test_len(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    assert len(matrix) == 2


def test_eq(sample_polars_df):
    matrix1 = Matrix(sample_polars_df)
    matrix2 = Matrix(sample_polars_df)
    assert matrix1 == matrix2


def test_eq_invalid_type(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    with pytest.raises(TypeError):
        assert matrix == "not a matrix"


def test_add_timeseries(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=4, freq="D"),
                "scenario3": [9, 10, 11, 12],
            }
        )
    )
    matrix.add(new_ts, "scenario3")
    assert "scenario3" in matrix.indexes


def test_add_dict(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    matrix.add(
        {
            "time": pd.date_range(start="2025-01-01", periods=4, freq="D"),
            "scenario3": [9, 10, 11, 12],
        },
        "scenario3",
    )
    assert "scenario3" in matrix.indexes


def test_delete_existing(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    matrix.delete("scenario1")
    assert "scenario1" not in matrix.indexes


def test_delete_non_existing(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    with pytest.raises(KeyError, match="No timeseries to delete"):
        matrix.delete("non_existing")


def test_get_matrix(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    df = matrix.get_matrix()
    assert isinstance(df, pl.DataFrame)


def test_from_file_parquet(tmp_path, sample_pandas_df):
    file_path = tmp_path / "matrix.parquet"
    sample_pandas_df.to_parquet(file_path, index=False)
    matrix = Matrix.from_file(file_path)
    assert matrix.indexes == ["scenario1", "scenario2"]
    assert matrix.matrix.shape == (4, 3)
