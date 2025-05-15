# test_matrix.py


import pandas as pd
import polars as pl
import pytest

from atlas.math.lazy_matrix import LazyMatrix
from atlas.math.matrix import Matrix
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
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
def sample_pandas_df_invalid_schema():
    return pd.DataFrame(
        {
            "time": pd.date_range(start="2025-01-01", periods=4, freq="D"),
            "scenario1": [1, 2, 3, 4],
            "scenario2": [5, 6, 7, 8],
            "invalid": ["A", "B", "C", "D"],
        }
    )


@pytest.fixture
def sample_polars_df_invalid_schema(sample_pandas_df_invalid_schema):
    return pl.from_pandas(sample_pandas_df_invalid_schema)


@pytest.fixture
def sample_polars_df(sample_pandas_df):
    return pl.from_pandas(sample_pandas_df)


@pytest.fixture
def sample_matrix(sample_polars_df):
    return Matrix(sample_polars_df)


def test_init_with_polars(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    assert matrix.indexes == ["scenario1", "scenario2"]
    assert matrix.matrix.shape == (3, 3)


def test_init_with_matrix(sample_matrix):
    matrix = Matrix(sample_matrix)
    assert matrix.indexes == ["scenario1", "scenario2"]
    assert matrix.matrix.shape == (3, 3)


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
    assert ts.shape == (3, 2)  # time + scenario1


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


def test_add_timeseries_already_existing_index(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=4, freq="D"),
                "value": [9, 10, 11, 12],
            }
        )
    )
    with pytest.raises(KeyError, match="Index scenario2 already exists in the matrix."):
        matrix.add(new_ts, "scenario2")


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


def test_from_file_csv(tmp_path, sample_pandas_df):
    file_path = tmp_path / "matrix.csv"
    sample_pandas_df.to_csv(file_path, index=False, sep=";")
    matrix = Matrix.from_file(file_path)
    assert matrix.indexes == ["scenario1", "scenario2"]
    assert matrix.matrix.shape == (4, 3)


def test_from_file_csv_str_input(tmp_path, sample_pandas_df):
    file_path = tmp_path / "matrix.csv"
    sample_pandas_df.to_csv(file_path, index=False, sep=";")
    matrix = Matrix.from_file(str(file_path))
    assert matrix.indexes == ["scenario1", "scenario2"]
    assert matrix.matrix.shape == (4, 3)


def test_from_file_with_filter(tmp_path):
    df = pl.DataFrame(
        {
            "region": ["FR", "FR", "DE", "DE"],
            "time": pd.date_range(start="2025-01-01", periods=4, freq="D"),
            "load": [1, 2, 3, 4],
        }
    )
    file_path = tmp_path / "filtered.parquet"
    df.write_parquet(file_path)
    matrix = Matrix.from_file(file_path, filters=("region", "FR"))
    assert "region" not in matrix.matrix.columns
    assert matrix.matrix.shape[0] == 2


def test_describe():
    df = pl.DataFrame(
        {
            "region": ["FR", "FR", "DE", "DE"],
            "time": pd.date_range(start="2025-01-01", periods=4, freq="D"),
            "load": [1, 2, 3, 4],
            "hydro": [4, 5, 6, 7],
        }
    )

    assert Matrix.describe(df) == {
        "shape": (4, 4),
        "memory_mb": "0.00",
        "datetime": {
            "column": "time",
            "min": "2025-01-01 00:00:00",
            "max": "2025-01-04 00:00:00",
            "nulls": 0,
        },
        "categorical": {"column": "region", "categories": ["DE", "FR"], "nulls": 0},
        "numeric_columns": ["load", "hydro"],
    }


def test_from_file_with_invalid_schema(tmp_path):
    df = pl.DataFrame(
        {
            "region": ["FR", "FR", "DE", "DE"],
            "time": pd.date_range(start="2025-01-01", periods=4, freq="D"),
            "load": [1, 2, 3, 4],
        }
    )

    with pytest.raises(ValueError, match="Matrix must have N columns one for datetime and N-1 for numerical values"):
        matrix = Matrix(df)


def test_to_file_csv(tmp_path, sample_polars_df):
    path = tmp_path / "out.csv"
    matrix = Matrix(sample_polars_df)
    matrix.to_file(path, file_format="csv")
    assert path.read_text().startswith("time;")


def test_to_file_parquet(tmp_path, sample_polars_df):
    path = tmp_path / "out.parquet"
    matrix = Matrix(sample_polars_df)
    matrix.to_file(path, file_format="parquet")
    assert path.exists()


def test_to_file_pickle(tmp_path, sample_polars_df):
    path = tmp_path / "out.pickle"
    matrix = Matrix(sample_polars_df)
    matrix.to_file(path, file_format="pickle")
    assert path.exists()


def test_to_file_invalid(tmp_path, sample_polars_df):
    path = tmp_path / "out.xls"
    matrix = Matrix(sample_polars_df)
    with pytest.raises(NotImplementedError, match="Format not supported"):
        matrix.to_file(path, file_format="xls")


def test_to_file_extension_mismatch(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    with pytest.raises(ValueError, match="Format and file extension don't match"):
        matrix.to_file("test.csv", file_format="parquet")


def test_to_lazy(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    lazy = matrix.to_lazy()
    assert isinstance(lazy, pl.LazyFrame)


def test_invalid_matrix_multiple_time_columns():
    df = pl.DataFrame(
        {
            "time1": pd.date_range("2025-01-01", periods=4),
            "time2": pd.date_range("2025-01-01", periods=4),
            "val": [1, 2, 3, 4],
        }
    )
    with pytest.raises(ValueError, match="exactly one time column"):
        Matrix(df)


@pytest.fixture
def sample_polars_df():
    return pl.DataFrame(
        {
            "time": pd.date_range(start="2025-01-01", periods=3, freq="D"),
            "scenario1": [10, 20, 30],
            "scenario2": [40, 50, 60],
        }
    )


def test_scenario_matrix_init(sample_polars_df):
    sm = ScenarioMatrix(sample_polars_df)
    assert isinstance(sm, Matrix)
    assert sm.indexes == ["scenario1", "scenario2"]
    assert sm.matrix.shape == (3, 3)


def test_scenario_matrix_repr(sample_polars_df):
    sm = ScenarioMatrix(sample_polars_df)
    repr_str = repr(sm)
    assert "Scenario Matrix" in repr_str
    assert "scenario1" in repr_str


def test_matrix_repr(sample_polars_df):
    sm = Matrix(sample_polars_df)
    repr_str = repr(sm)
    assert "Matrix" in repr_str
    assert "scenario1" in repr_str


def test_lazy_scenario_matrix_init(sample_polars_df):
    lazy_df = sample_polars_df.lazy()
    lsm = LazyScenarioMatrix(lazy_df)
    assert lsm.matrix.collect().shape == (3, 3)
    assert lsm.indexes == ["scenario1", "scenario2"]


def test_lazy_scenario_matrix_repr(sample_polars_df):
    lazy_df = sample_polars_df.lazy()
    lsm = LazyScenarioMatrix(lazy_df)
    repr_str = repr(lsm)
    assert "LazyScenarioMatrix with schema" in repr_str


def test_lazy_matrix_repr(sample_polars_df):
    lazy_df = sample_polars_df.lazy()
    lsm = LazyMatrix(lazy_df)
    repr_str = repr(lsm)
    assert "LazyMatrix with schema" in repr_str


def test_get_indexes_invalid_schema(sample_polars_df_invalid_schema):
    with pytest.raises(
        ValueError,
        match="LazyMatrix must have N columns one for datetime and N-1 for numerical values",
    ):
        LazyScenarioMatrix(sample_polars_df_invalid_schema.lazy())

    with pytest.raises(
        ValueError,
        match="LazyMatrix must have N columns one for datetime and N-1 for numerical values",
    ):
        LazyMatrix(sample_polars_df_invalid_schema.lazy())
