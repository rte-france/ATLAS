from datetime import datetime

import polars as pl
import pytest

from atlas.math.lazy_matrix import LazyScenarioMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.matrix import ScenarioMatrix


@pytest.fixture
def simple_lazyframe():
    return pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "1": [1.0, 2.0], "2": [3.0, 4.0]}).lazy()


@pytest.fixture
def simple_frame():
    return pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "1": [1.0, 2.0], "2": [3.0, 4.0]})


@pytest.fixture
def simple_matrix():
    return ScenarioMatrix(
        pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "1": [1.0, 2.0], "2": [3.0, 4.0]}).lazy()
    )


def test_init_from_lazyframe(simple_lazyframe):
    lm = LazyScenarioMatrix(simple_lazyframe, timezone="UTC")
    data = lm.get_matrix().collect()
    assert "time" in data.columns
    assert data["time"].dtype.time_unit == "us"


def test_init_from_matrix(simple_matrix):
    lm = LazyScenarioMatrix(simple_matrix, timezone="UTC")
    assert isinstance(lm.get_matrix(), pl.LazyFrame)
    assert lm.timezone == "UTC"  # From ScenarioMatrix


def test_init_from_lazymatrix(simple_lazyframe):
    lm1 = LazyScenarioMatrix(simple_lazyframe, timezone="UTC")
    lm2 = LazyScenarioMatrix(lm1)
    assert lm2.timezone == "UTC"
    assert lm2.get_matrix().collect().equals(lm1.get_matrix().collect())


def test_invalid_timezone(simple_lazyframe):
    with pytest.raises(ValueError, match="Invalid timezone: INVALID_TZ"):
        LazyScenarioMatrix(simple_lazyframe, timezone="INVALID_TZ")


def test_invalid_type():
    with pytest.raises(TypeError):
        LazyScenarioMatrix("not a valid input")


def test_invalid_schema():
    df = pl.DataFrame({"value": [1, 2, 3]}).lazy()
    with pytest.raises(ValueError, match="must have exactly one datetime column"):
        LazyScenarioMatrix(df)


def test_get_indexes(simple_lazyframe):
    lm = LazyScenarioMatrix(simple_lazyframe)
    assert sorted(lm.indexes) == ["1", "2"]


def test_collect_returns_matrix(simple_lazyframe):
    lm = LazyScenarioMatrix(simple_lazyframe)
    mat = lm.collect()
    assert isinstance(mat, ScenarioMatrix)
    assert mat.shape == (2, 3)


def test_collect_returns_scenariomatrix(simple_lazyframe):
    lm = LazyScenarioMatrix(simple_lazyframe)
    mat = lm.collect()
    assert isinstance(mat, ScenarioMatrix)
    assert mat.shape == (2, 3)


def test_from_file_parquet(tmp_path, simple_frame):
    pq_path = tmp_path / "data.parquet"

    simple_frame.write_parquet(pq_path)

    lm = LazyScenarioMatrix.from_file(pq_path)
    assert isinstance(lm, LazyScenarioMatrix)


def test_from_file_invalid_format(tmp_path):
    bad_path = tmp_path / "data.txt"
    bad_path.write_text("some text")
    with pytest.raises(NotImplementedError, match="Atlas file should be a csv or parquet."):
        LazyScenarioMatrix.from_file(bad_path)


def test_add_timeseries(simple_lazyframe):
    """Test adding a timeseries."""
    lm = LazyScenarioMatrix(simple_lazyframe)

    ts_data = {"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [5.0, 6.0]}
    lm.add(ts_data, "3")

    assert "3" in lm.indexes
    assert len(lm.indexes) == 3


def test_add_existing_index_error(simple_lazyframe):
    """Test adding existing index raises error."""
    lm = LazyScenarioMatrix(simple_lazyframe)
    ts_data = {"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [5.0, 6.0]}

    with pytest.raises(KeyError, match="Index 1 already exists"):
        lm.add(ts_data, "1")


def test_delete_index(simple_lazyframe):
    """Test deleting an index."""
    lm = LazyScenarioMatrix(simple_lazyframe)

    lm.delete("1")

    assert "1" not in lm.indexes
    assert "2" in lm.indexes
    assert len(lm.indexes) == 1


def test_delete_non_existing_error(simple_lazyframe):
    """Test deleting non-existing index raises error."""
    lm = LazyScenarioMatrix(simple_lazyframe)

    with pytest.raises(KeyError, match="No timeseries to delete at index: missing"):
        lm.delete("missing")


def test_add_after_delete(simple_lazyframe):
    """Test add after delete works."""
    lm = LazyScenarioMatrix(simple_lazyframe)

    lm.delete("1")
    ts_data = {"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [10.0, 20.0]}
    lm.add(ts_data, "1")

    assert "1" in lm.indexes


def test_preserves_lazy_evaluation(simple_lazyframe):
    """Test that add and delete preserve lazy evaluation."""
    lm = LazyScenarioMatrix(simple_lazyframe)

    assert isinstance(lm.get_matrix(), pl.LazyFrame)

    ts_data = {"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [5.0, 6.0]}
    lm.add(ts_data, "3")
    assert isinstance(lm.get_matrix(), pl.LazyFrame)

    lm.delete("1")
    assert isinstance(lm.get_matrix(), pl.LazyFrame)


def test_select(simple_lazyframe):
    """Test select() returns a LazyTimeseries."""

    matrix = LazyScenarioMatrix(simple_lazyframe)
    ts = matrix.select("1")

    # Verify it returns a LazyTimeseries
    assert isinstance(ts, LazyTimeseries)

    # Collect and check the shape
    collected = ts.collect()
    assert collected.to_frame().shape == (2, 2)
