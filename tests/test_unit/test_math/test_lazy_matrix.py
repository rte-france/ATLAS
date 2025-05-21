from datetime import datetime

import polars as pl
import pytest

from atlas.math.lazy_matrix import LazyMatrix
from atlas.math.matrix import Matrix
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix


@pytest.fixture
def simple_lazyframe():
    return pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "1": [1.0, 2.0], "2": [3.0, 4.0]}).lazy()


@pytest.fixture
def simple_frame():
    return pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "1": [1.0, 2.0], "2": [3.0, 4.0]})


@pytest.fixture
def simple_matrix():
    return Matrix(
        pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "1": [1.0, 2.0], "2": [3.0, 4.0]}).lazy()
    )


def test_init_from_lazyframe(simple_lazyframe):
    lm = LazyMatrix(simple_lazyframe, timezone="UTC")
    data = lm.get_matrix().collect()
    assert "time" in data.columns
    assert data["time"].dtype.time_unit == "us"


def test_init_from_matrix(simple_matrix):
    lm = LazyMatrix(simple_matrix, timezone="UTC")
    assert isinstance(lm.get_matrix(), pl.LazyFrame)
    assert lm.timezone == "UTC"  # From Matrix


def test_init_from_lazymatrix(simple_lazyframe):
    lm1 = LazyMatrix(simple_lazyframe, timezone="UTC")
    lm2 = LazyMatrix(lm1)
    assert lm2.timezone == "UTC"
    assert lm2.get_matrix().collect().equals(lm1.get_matrix().collect())


def test_invalid_timezone(simple_lazyframe):
    with pytest.raises(ValueError, match="Invalid timezone: INVALID_TZ"):
        LazyMatrix(simple_lazyframe, timezone="INVALID_TZ")


def test_invalid_type():
    with pytest.raises(TypeError):
        LazyMatrix("not a valid input")


def test_invalid_schema():
    df = pl.DataFrame({"value": [1, 2, 3]}).lazy()
    with pytest.raises(ValueError, match="must have exactly one datetime column"):
        LazyMatrix(df)


def test_get_indexes(simple_lazyframe):
    lm = LazyMatrix(simple_lazyframe)
    assert sorted(lm.indexes) == ["1", "2"]


def test_collect_returns_matrix(simple_lazyframe):
    lm = LazyMatrix(simple_lazyframe)
    mat = lm.collect()
    assert isinstance(mat, Matrix)
    assert mat.shape == (2, 3)


def test_collect_returns_scenariomatrix(simple_lazyframe):
    lm = LazyScenarioMatrix(simple_lazyframe)
    mat = lm.collect()
    assert isinstance(mat, ScenarioMatrix)
    assert mat.shape == (2, 3)


def test_from_file_parquet(tmp_path, simple_frame):
    pq_path = tmp_path / "data.parquet"

    simple_frame.write_parquet(pq_path)

    lm = LazyMatrix.from_file(pq_path)
    assert isinstance(lm, LazyMatrix)


def test_from_file_invalid_format(tmp_path):
    bad_path = tmp_path / "data.txt"
    bad_path.write_text("some text")
    with pytest.raises(ValueError, match="Unsupported file format"):
        LazyMatrix.from_file(bad_path)
