# test_matrix.py


import pandas as pd
import plotly.graph_objects as go
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
            "time": pd.date_range(start="2025-01-01", periods=3, freq="D"),
            "scenario1": [1, 2, 3],
            "scenario2": [5, 6, 7],
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
    assert matrix.matrix.shape == (3, 3)


def test_invalid_timezone(sample_polars_df):
    with pytest.raises(ValueError, match="Invalid timezone"):
        Matrix(sample_polars_df, timezone="Mars/Phobos")


def test_getitem(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    ts = matrix["scenario1"]
    assert ts.to_frame().shape == (3, 2)


def test_select(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    ts = matrix.select("scenario1")
    assert ts.to_frame().shape == (3, 2)


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


def test_add_polars_dataframe(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    new_df = pl.DataFrame(
        {
            "time": pd.date_range(start="2025-01-01", periods=4, freq="D"),
            "scenario3": [9, 10, 11, 12],
        }
    )
    matrix.add(new_df, "scenario3")
    assert "scenario3" in matrix.indexes
    assert len(matrix.indexes) == 3


def test_add_pandas_dataframe(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    new_df = pd.DataFrame(
        {
            "time": pd.date_range(start="2025-01-01", periods=4, freq="D"),
            "scenario3": [9, 10, 11, 12],
        }
    )
    matrix.add(new_df, "scenario3")
    assert "scenario3" in matrix.indexes
    assert len(matrix.indexes) == 3


def test_delete_existing(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    matrix.delete("scenario1")
    assert "scenario1" not in matrix.indexes


def test_delete_non_existing(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    with pytest.raises(KeyError, match="No timeseries to delete"):
        matrix.delete("non_existing")


def test_delete_all_scenarios(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    initial_count = len(matrix.indexes)

    # Delete all scenarios
    for index in matrix.indexes.copy():
        matrix.delete(index)

    assert len(matrix.indexes) == 0
    assert matrix.matrix.shape == (3, 1)  # Only time column remains
    assert matrix.matrix.columns == ["time"]


def test_delete_and_readd(sample_polars_df):
    matrix = Matrix(sample_polars_df)

    # Delete scenario1
    matrix.delete("scenario1")
    assert "scenario1" not in matrix.indexes
    assert len(matrix.indexes) == 1

    # Re-add scenario1 with different data
    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=4, freq="D"),
                "value": [100, 200, 300, 400],
            }
        )
    )
    matrix.add(new_ts, "scenario1")
    assert "scenario1" in matrix.indexes
    assert len(matrix.indexes) == 2

    # Verify the new data
    retrieved_ts = matrix["scenario1"]
    assert retrieved_ts.to_frame().select("value").to_pandas()["value"].iloc[0] == 100


def test_get_matrix(sample_polars_df):
    matrix = Matrix(sample_polars_df)
    df = matrix.get_matrix()
    assert isinstance(df, pl.DataFrame)


def test_from_file_parquet(tmp_path, sample_pandas_df):
    file_path = tmp_path / "matrix.parquet"
    sample_pandas_df.to_parquet(file_path, index=False)
    matrix = Matrix.from_file(file_path)
    assert matrix.indexes == ["scenario1", "scenario2"]
    assert matrix.matrix.shape == (3, 3)


def test_from_file_csv(tmp_path, sample_pandas_df):
    file_path = tmp_path / "matrix.csv"
    sample_pandas_df.to_csv(file_path, index=False, sep=";")
    matrix = Matrix.from_file(file_path)
    assert matrix.indexes == ["scenario1", "scenario2"]
    assert matrix.matrix.shape == (3, 3)


def test_from_file_csv_str_input(tmp_path, sample_pandas_df):
    file_path = tmp_path / "matrix.csv"
    sample_pandas_df.to_csv(file_path, index=False, sep=";")
    matrix = Matrix.from_file(str(file_path))
    assert matrix.indexes == ["scenario1", "scenario2"]
    assert matrix.matrix.shape == (3, 3)


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


def test_to_file_with_attribute_csv(tmp_path, sample_polars_df):
    """Test to_file_with_attribute with CSV format."""
    path = tmp_path / "test_attr.csv"
    matrix = Matrix(sample_polars_df)

    # Write file with attribute
    matrix.to_file_with_attribute(path, attribute="power", file_format="csv")
    assert path.exists()

    # Check if file contains attribute column
    df = pl.read_csv(path, separator=";")
    assert "attribute" in df.columns
    assert df["attribute"].unique().to_list() == ["power"]
    assert len(df) == len(matrix.dataframe)


def test_to_file_with_attribute_concatenate(tmp_path, sample_polars_df):
    """Test to_file_with_attribute with concatenation of existing file."""
    path = tmp_path / "test_concat.parquet"

    # Create first matrix
    matrix1 = Matrix(sample_polars_df)

    # Write first matrix with attribute "power"
    matrix1.to_file_with_attribute(path, attribute="power", file_format="parquet")

    # Create second matrix with different data
    df2 = pl.DataFrame(
        {
            "time": pd.date_range(start="2025-01-04", periods=2, freq="D"),
            "scenario1": [4, 5],
            "scenario2": [8, 9],
        }
    )
    matrix2 = Matrix(df2)

    # Write second matrix with attribute "capacity"
    matrix2.to_file_with_attribute(path, attribute="capacity", file_format="parquet")

    # Read concatenated file
    df_concat = pl.read_parquet(path)

    # Check that both attributes are present
    assert "attribute" in df_concat.columns
    assert set(df_concat["attribute"].unique().to_list()) == {"power", "capacity"}

    # Check total length
    assert len(df_concat) == len(matrix1.dataframe) + len(matrix2.dataframe)


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


def test_matrix_plot_returns_valid_figure(sample_polars_df):
    matrix = Matrix(sample_polars_df)

    fig = matrix.plot()

    assert isinstance(fig, go.Figure)

    assert len(fig.data) == 2

    sliders = fig.layout.sliders
    assert sliders is not None and len(sliders) == 1

    slider_steps = sliders[0]["steps"]
    assert len(slider_steps) == 2
    assert all("label" in step for step in slider_steps)


def test_add_different_time_ranges():
    # Test adding timeseries with different time ranges
    initial_df = pl.DataFrame(
        {
            "time": pd.date_range(start="2025-01-01", periods=3, freq="D"),
            "scenario1": [1, 2, 3],
        }
    )
    matrix = Matrix(initial_df)

    # Add timeseries with different time range
    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pd.date_range(start="2025-01-02", periods=4, freq="D"),  # Different start and length
                "value": [10, 20, 30, 40],
            }
        )
    )
    matrix.add(new_ts, "scenario2")

    assert "scenario2" in matrix.indexes
    # The matrix should contain the union of both time ranges
    assert matrix.matrix.shape[0] == 5  # 2025-01-01 to 2025-01-05


def test_add_empty_timeseries():
    initial_df = pl.DataFrame(
        {
            "time": pd.date_range(start="2025-01-01", periods=3, freq="D"),
            "scenario1": [1, 2, 3],
        }
    )
    matrix = Matrix(initial_df)

    # Add empty timeseries
    empty_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=0, freq="D"),
                "value": [],
            },
            schema={"time": pl.Datetime, "value": pl.Float64},
        )
    )

    matrix.add(empty_ts, "empty_scenario")
    assert "empty_scenario" in matrix.indexes
    # The matrix should still have the original 3 rows
    assert matrix.matrix.shape[0] == 3


def test_scenario_matrix_set_frequency_upsample():
    """Test upsampling scenario matrix from daily to hourly frequency."""
    # Create daily data
    df = pl.DataFrame(
        {
            "time": pd.date_range(start="2025-01-01", periods=3, freq="D"),
            "scenario1": [10.0, 20.0, 30.0],
            "scenario2": [100.0, 200.0, 300.0],
        }
    )
    sm = ScenarioMatrix(df)

    # Upsample to hourly (should interpolate)
    result = sm.set_frequency("1h", inplace=False)

    # Should have 24*2 + 1 = 49 hours (from start of day 1 to start of day 3)
    assert result.matrix.shape[0] == 49
    assert "scenario1" in result.indexes
    assert "scenario2" in result.indexes

    # Check that original is unchanged (inplace=False)
    assert sm.matrix.shape[0] == 3


def test_matrix_set_frequency_downsample():
    """Test downsampling scenario matrix from hourly to daily frequency."""
    # Create hourly data for 2 days
    hourly_times = pd.date_range(start="2025-01-01", periods=48, freq="h")
    df = pl.DataFrame(
        {
            "time": hourly_times,
            "scenario1": list(range(48)),  # 0, 1, 2, ..., 47
            "scenario2": [x * 2 for x in range(48)],  # 0, 2, 4, ..., 94
        }
    )
    sm = Matrix(df)

    # Downsample to daily (should aggregate by mean)
    result = sm.set_frequency("1d", inplace=False)

    # Should have 2 days
    assert result.matrix.shape[0] == 2
    assert "scenario1" in result.indexes
    assert "scenario2" in result.indexes

    # Check that values are averaged correctly
    # First day: mean of 0-23 = 11.5, Second day: mean of 24-47 = 35.5
    values1 = result.matrix.select("scenario1").to_series().to_list()
    assert abs(values1[0] - 11.5) < 0.001
    assert abs(values1[1] - 35.5) < 0.001


def test_matrix_set_frequency_same():
    """Test set_frequency with same frequency (should return unchanged)."""
    df = pl.DataFrame(
        {
            "time": pd.date_range(start="2025-01-01", periods=3, freq="D"),
            "scenario1": [10.0, 20.0, 30.0],
            "scenario2": [100.0, 200.0, 300.0],
        }
    )
    sm = Matrix(df)

    # Set to same frequency
    result = sm.set_frequency("1d", inplace=False)

    # Should be unchanged
    assert result.matrix.shape[0] == 3
    assert result.matrix.equals(sm.matrix)


def test_matrix_set_frequency_inplace():
    """Test set_frequency with inplace=True."""
    df = pl.DataFrame(
        {
            "time": pd.date_range(start="2025-01-01", periods=24, freq="h"),
            "scenario1": list(range(24)),
            "scenario2": [x * 2 for x in range(24)],
        }
    )
    sm = Matrix(df)
    original_shape = sm.matrix.shape

    # Downsample inplace
    result = sm.set_frequency("1d", inplace=True)

    # Should return self and modify original
    assert result is sm
    assert sm.matrix.shape[0] == 1  # One day
    assert sm.matrix.shape != original_shape


def test_matrix_set_frequency_empty():
    """Test set_frequency on empty matrix."""
    # Create empty matrix with at least one scenario column to satisfy validation
    df = pl.DataFrame(
        {"time": [], "scenario1": []}, schema={"time": pl.Datetime("us", time_zone="UTC"), "scenario1": pl.Float64()}
    )
    sm = Matrix(df)

    result = sm.set_frequency("1h", inplace=False)

    assert result.matrix.shape[0] == 0
    assert len(result.indexes) == 1  # Has scenario1 column
