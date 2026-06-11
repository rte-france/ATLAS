from datetime import datetime

import pandas as pd
import pendulum
import polars as pl
import pytest

from atlas.core.math.lazy_matrix import LazyScenarioMatrix
from atlas.core.math.lazy_timeseries import LazyTimeseries
from atlas.core.math.matrix import ScenarioMatrix
from atlas.core.math.timeseries import Timeseries


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


@pytest.fixture
def hourly_lazyframe():
    """3-column LazyFrame with hourly data (useful for set_frequency tests)."""
    return pl.DataFrame(
        {
            "time": [
                datetime(2023, 1, 1, 0, 0),
                datetime(2023, 1, 1, 1, 0),
                datetime(2023, 1, 1, 2, 0),
                datetime(2023, 1, 1, 3, 0),
            ],
            "A": [1.0, 2.0, 3.0, 4.0],
            "B": [10.0, 20.0, 30.0, 40.0],
        }
    ).lazy()


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


# ============================================================
# Properties
# ============================================================


class TestProperties:
    def test_lazyframe_property(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        assert isinstance(lm.lazyframe, pl.LazyFrame)

    def test_dataframe_property(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        assert isinstance(lm.dataframe, pl.LazyFrame)

    def test_index_property(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        assert sorted(lm.index) == ["1", "2"]

    def test_metadata_property(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        meta = lm.metadata
        assert isinstance(meta, dict)
        assert "shape" in meta


# ============================================================
# __repr__, __eq__, __contains__, __len__, __getitem__
# ============================================================


class TestDunders:
    def test_repr(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        r = repr(lm)
        assert "LazyScenarioMatrix with schema" in r

    def test_eq_equal(self, simple_lazyframe):
        lm1 = LazyScenarioMatrix(simple_lazyframe)
        lm2 = LazyScenarioMatrix(simple_lazyframe)
        assert lm1 == lm2

    def test_eq_not_equal(self, simple_lazyframe):
        lm1 = LazyScenarioMatrix(simple_lazyframe)
        other_lf = pl.DataFrame(
            {"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "1": [9.0, 9.0], "2": [9.0, 9.0]}
        ).lazy()
        lm2 = LazyScenarioMatrix(other_lf)
        assert not (lm1 == lm2)

    def test_eq_raises_for_non_matrix(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        with pytest.raises(TypeError):
            assert lm == "not a matrix"

    def test_contains_existing(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        assert "1" in lm
        assert "2" in lm

    def test_contains_missing(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        assert "99" not in lm

    def test_len(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        assert len(lm) == 2

    def test_len_after_delete(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        lm.delete("1")
        assert len(lm) == 1

    def test_getitem_returns_lazy_timeseries(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        ts = lm["1"]
        assert isinstance(ts, LazyTimeseries)

    def test_getitem_values(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        ts = lm["1"]
        assert ts.values == [1.0, 2.0]

    def test_getitem_missing_raises(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        with pytest.raises(KeyError):
            lm["missing"]


# ============================================================
# _get_shape / .shape
# ============================================================


class TestGetShape:
    def test_shape_basic(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        # 2 rows, 3 columns (time + "1" + "2")
        assert lm.shape == (2, 3)

    def test_shape_after_add(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        lm.add({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [5.0, 6.0]}, "3")
        assert lm.shape == (2, 4)

    def test_shape_after_delete(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        lm.delete("1")
        assert lm.shape == (2, 2)


# ============================================================
# select() – additional cases
# ============================================================


class TestSelect:
    def test_select_correct_values(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        ts = lm.select("2")
        assert ts.values == [3.0, 4.0]

    def test_select_preserves_timezone(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe, timezone="Europe/Paris")
        ts = lm.select("1")
        assert ts.timezone == "Europe/Paris"

    def test_select_missing_raises(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        with pytest.raises(KeyError, match="not found"):
            lm.select("missing")


# ============================================================
# replace()
# ============================================================


class TestReplace:
    def test_replace_updates_values(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        new_ts = {"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [99.0, 88.0]}
        lm.replace("1", new_ts)
        assert lm["1"].values == [99.0, 88.0]

    def test_replace_preserves_other_columns(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        new_ts = {"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [99.0, 88.0]}
        lm.replace("1", new_ts)
        assert "2" in lm.indexes
        assert lm["2"].values == [3.0, 4.0]

    def test_replace_missing_raises(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        with pytest.raises(KeyError):
            lm.replace("missing", {"time": [datetime(2023, 1, 1)], "value": [1.0]})


# ============================================================
# add() – various input types
# ============================================================


class TestAddInputTypes:
    def test_add_lazy_timeseries(self, simple_lazyframe):
        # When a LazyTimeseries is passed, the join uses its internal "value" column name.
        # The index argument is used only for KeyError checking, not for renaming.
        lm = LazyScenarioMatrix(simple_lazyframe)
        lt = LazyTimeseries(
            pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [7.0, 8.0]}).lazy()
        )
        lm.add(lt, "value")
        assert "value" in lm.indexes

    def test_add_polars_lazyframe(self, simple_lazyframe):
        # When a raw LazyFrame is passed, the time column must match the matrix timezone (UTC).
        lm = LazyScenarioMatrix(simple_lazyframe)
        lf = (
            pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "3": [7.0, 8.0]})
            .lazy()
            .with_columns(pl.col("time").cast(pl.Datetime("us", "UTC")))
        )
        lm.add(lf, "3")
        assert "3" in lm.indexes

    def test_add_polars_dataframe(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        df = pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [7.0, 8.0]})
        lm.add(df, "3")
        assert "3" in lm.indexes

    def test_add_pandas_dataframe(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        df = pd.DataFrame(
            {
                "time": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
                "value": [7.0, 8.0],
            }
        )
        lm.add(df, "3")
        assert "3" in lm.indexes

    def test_add_timeseries(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        ts = Timeseries(pl.DataFrame({"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [7.0, 8.0]}))
        lm.add(ts, "3")
        assert "3" in lm.indexes


# ============================================================
# set_frequency()
# ============================================================


class TestSetFrequency:
    def test_set_frequency_inplace(self, hourly_lazyframe):
        lm = LazyScenarioMatrix(hourly_lazyframe)
        result = lm.set_frequency("2h")
        assert result is lm
        collected = lm.collect()
        # 4 hourly rows downsampled to 2h → 2 rows
        assert collected.shape[0] == 2

    def test_set_frequency_not_inplace(self, hourly_lazyframe):
        lm = LazyScenarioMatrix(hourly_lazyframe)
        original_shape = lm.collect().shape
        result = lm.set_frequency("2h", inplace=False)
        assert result is not lm
        assert isinstance(result, LazyScenarioMatrix)
        # Original unchanged
        assert lm.collect().shape == original_shape

    def test_set_frequency_returns_lazymatrix(self, hourly_lazyframe):
        lm = LazyScenarioMatrix(hourly_lazyframe)
        result = lm.set_frequency("2h", inplace=False)
        assert isinstance(result, LazyScenarioMatrix)

    def test_set_frequency_pendulum_duration(self, hourly_lazyframe):
        lm = LazyScenarioMatrix(hourly_lazyframe)
        result = lm.set_frequency(pendulum.duration(hours=2), inplace=False)
        assert result.collect().shape[0] == 2


# ============================================================
# to_lazy()
# ============================================================


class TestToLazy:
    def test_to_lazy_returns_lazyframe(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        assert isinstance(lm.to_lazy(), pl.LazyFrame)

    def test_to_lazy_data_matches(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        assert lm.to_lazy().collect().equals(lm.get_matrix().collect())


# ============================================================
# describe()
# ============================================================


class TestDescribe:
    def test_describe_returns_dict(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        d = lm.describe()
        assert isinstance(d, dict)

    def test_describe_has_shape(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        d = lm.describe()
        assert "shape" in d
        assert d["shape"] == (2, 3)


# ============================================================
# to_file() / to_file_with_attribute()
# ============================================================


class TestIO:
    def test_to_file_csv(self, simple_lazyframe, tmp_path):
        lm = LazyScenarioMatrix(simple_lazyframe)
        path = tmp_path / "out.csv"
        lm.to_file(path, file_format="csv")
        assert path.exists()

    def test_to_file_parquet(self, simple_lazyframe, tmp_path):
        lm = LazyScenarioMatrix(simple_lazyframe)
        path = tmp_path / "out.parquet"
        lm.to_file(path, file_format="parquet")
        assert path.exists()

    def test_to_file_roundtrip(self, simple_lazyframe, tmp_path):
        lm = LazyScenarioMatrix(simple_lazyframe)
        path = tmp_path / "out.parquet"
        lm.to_file(path, file_format="parquet")
        loaded = LazyScenarioMatrix.from_file(path)
        assert loaded.collect().shape == lm.collect().shape

    def test_to_file_with_attribute(self, simple_lazyframe, tmp_path):
        lm = LazyScenarioMatrix(simple_lazyframe)
        path = tmp_path / "out.csv"
        lm.to_file_with_attribute(path, attribute="scenario_A")
        assert path.exists()

    def test_from_file_csv(self, simple_frame, tmp_path):
        path = tmp_path / "data.csv"
        simple_frame.write_csv(path, separator=";")
        lm = LazyScenarioMatrix.from_file(path)
        assert isinstance(lm, LazyScenarioMatrix)
        assert lm.collect().shape == (2, 3)

    def test_from_file_with_filter(self, tmp_path):
        df = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1), datetime(2023, 1, 2)] * 2,
                "category": ["A", "A", "B", "B"],
                "value": [1.0, 2.0, 3.0, 4.0],
            }
        )
        path = tmp_path / "data.parquet"
        df.write_parquet(path)
        lm = LazyScenarioMatrix.from_file(path, filters=("category", "A"))
        assert lm.collect().shape[0] == 2

    def test_from_file_with_timezone(self, simple_frame, tmp_path):
        path = tmp_path / "data.parquet"
        simple_frame.write_parquet(path)
        lm = LazyScenarioMatrix.from_file(path, timezone="Europe/Paris")
        assert lm.timezone == "Europe/Paris"


# ============================================================
# plot()
# ============================================================


class TestPlot:
    def test_plot_returns_figure(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        fig = lm.plot(title="Test")
        assert hasattr(fig, "data")
        assert hasattr(fig, "layout")

    def test_plot_title(self, simple_lazyframe):
        lm = LazyScenarioMatrix(simple_lazyframe)
        fig = lm.plot(title="My Plot")
        assert fig.layout.title.text == "My Plot"


# ============================================================
# Init – additional edge cases
# ============================================================


class TestInitEdgeCases:
    def test_init_renames_time_column(self):
        """LazyFrame with non-standard datetime column name is renamed to 'time'."""
        lf = pl.DataFrame({"timestamp": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "val": [1.0, 2.0]}).lazy()
        lm = LazyScenarioMatrix(lf)
        assert "time" in lm.get_matrix().collect().columns

    def test_init_mixed_non_numeric_column_raises(self):
        """LazyFrame with a non-numeric, non-temporal extra column raises ValueError."""
        lf = pl.DataFrame(
            {
                "time": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
                "val": [1.0, 2.0],
                "label": ["a", "b"],
            }
        ).lazy()
        with pytest.raises(ValueError):
            LazyScenarioMatrix(lf)

    def test_init_copies_timezone_from_source(self, simple_matrix):
        """When constructing from ScenarioMatrix, timezone is inherited."""
        lm = LazyScenarioMatrix(simple_matrix)
        assert lm.timezone == simple_matrix.timezone

    def test_init_from_lazymatrix_copies_timezone(self, simple_lazyframe):
        """When constructing from LazyScenarioMatrix, timezone is inherited."""
        lm1 = LazyScenarioMatrix(simple_lazyframe, timezone="America/New_York")
        lm2 = LazyScenarioMatrix(lm1)
        assert lm2.timezone == "America/New_York"


# ============================================================
# inplace parameter
# ============================================================


class TestInplace:
    @pytest.fixture
    def lm(self, simple_lazyframe):
        return LazyScenarioMatrix(simple_lazyframe)

    @pytest.fixture
    def new_ts_data(self):
        return {"time": [datetime(2023, 1, 1), datetime(2023, 1, 2)], "value": [99.0, 100.0]}

    def test_add_not_inplace_returns_new_matrix(self, lm, new_ts_data):
        result = lm.add(new_ts_data, "3", inplace=False)
        assert isinstance(result, LazyScenarioMatrix)
        assert "3" in result.indexes
        assert "3" not in lm.indexes

    def test_add_not_inplace_preserves_original_indexes(self, lm, new_ts_data):
        original_indexes = lm.indexes.copy()
        lm.add(new_ts_data, "3", inplace=False)
        assert lm.indexes == original_indexes

    def test_add_inplace_returns_self(self, lm, new_ts_data):
        result = lm.add(new_ts_data, "3", inplace=True)
        assert result is lm
        assert "3" in lm.indexes

    def test_delete_not_inplace_returns_new_matrix(self, lm):
        result = lm.delete("1", inplace=False)
        assert isinstance(result, LazyScenarioMatrix)
        assert "1" not in result.indexes
        assert "1" in lm.indexes

    def test_delete_not_inplace_preserves_other_indexes(self, lm):
        result = lm.delete("1", inplace=False)
        assert "2" in result.indexes
        assert len(result.indexes) == 1

    def test_delete_inplace_returns_self(self, lm):
        result = lm.delete("1", inplace=True)
        assert result is lm
        assert "1" not in lm.indexes

    def test_replace_not_inplace_returns_new_matrix(self, lm, new_ts_data):
        result = lm.replace("1", new_ts_data, inplace=False)
        assert isinstance(result, LazyScenarioMatrix)
        assert "1" in result.indexes

    def test_replace_not_inplace_original_data_unchanged(self, lm, new_ts_data):
        original_values = lm.collect()["1"].to_frame()["value"].to_list()
        lm.replace("1", new_ts_data, inplace=False)
        assert lm.collect()["1"].to_frame()["value"].to_list() == original_values

    def test_replace_not_inplace_result_has_new_data(self, lm, new_ts_data):
        result = lm.replace("1", new_ts_data, inplace=False)
        assert result.collect()["1"].to_frame()["value"].to_list() == [99.0, 100.0]

    def test_replace_inplace_returns_self(self, lm, new_ts_data):
        result = lm.replace("1", new_ts_data, inplace=True)
        assert result is lm
        assert lm.collect()["1"].to_frame()["value"].to_list() == [99.0, 100.0]
