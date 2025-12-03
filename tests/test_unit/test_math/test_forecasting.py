import os
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd
import pendulum
import polars as pl
import pytest

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_matrix import LazyMatrix
from atlas.math.timeseries import Timeseries


@pytest.fixture
def hourly_df():
    """Fixture for hourly data with two forecasts."""
    return pl.DataFrame(
        {
            "time": pl.datetime_range(
                start=datetime(2025, 1, 1, 0, 0, 0),
                end=datetime(2025, 1, 1, 4, 0, 0),
                interval="1h",
                time_unit="us",
                eager=True,
            ),
            "2025-01-01 00:00:00": [1, 2, 3, 4, 5],
            "2025-01-01 01:00:00": [6, 7, 8, 9, 10],
        }
    )


@pytest.fixture
def filtered_df():
    """Fixture for data with a filter column."""
    return pl.DataFrame(
        {
            "time": pl.datetime_range(
                start=datetime(2025, 1, 1, 0, 0, 0),
                end=datetime(2025, 1, 1, 4, 0, 0),
                interval="1h",
                time_unit="us",
                eager=True,
            ),
            "scenario": ["A", "A", "A", "A", "A"],
            "2025-01-01 00:00:00": [1, 2, 3, 4, 5],
            "2025-01-01 01:00:00": [6, 7, 8, 9, 10],
        }
    )


def test_init_and_sorting(hourly_df):
    matrix = ForecastingMatrix(hourly_df)
    assert isinstance(matrix, ForecastingMatrix)
    assert matrix.indexes == ["2025-01-01 00:00:00", "2025-01-01 01:00:00"]
    assert matrix.matrix.columns == ["time", "2025-01-01 00:00:00", "2025-01-01 01:00:00"]


def test_add_timeseries(hourly_df):
    matrix = ForecastingMatrix(hourly_df)

    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 3, 0, 0),
                    datetime(2025, 1, 1, 7, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "scenario3": [11, 12, 13, 14, 15],
            }
        )
    )

    matrix.add(new_ts, datetime(2025, 1, 1, 2, 0, 0))

    # Check new index exists, sorted
    assert "2025-01-01 02:00:00" in matrix.indexes
    assert matrix.matrix.columns == [
        "time",
        "2025-01-01 00:00:00",
        "2025-01-01 01:00:00",
        "2025-01-01 02:00:00",
    ]

    matrix.add(new_ts, "2025-01-01 03:00:00")

    # Check new index exists, sorted
    assert "2025-01-01 03:00:00" in matrix.indexes
    assert matrix.matrix.columns == [
        "time",
        "2025-01-01 00:00:00",
        "2025-01-01 01:00:00",
        "2025-01-01 02:00:00",
        "2025-01-01 03:00:00",
    ]


def test_contains_with_string_index(hourly_df):
    """Test the __contains__ method with string index."""
    matrix = ForecastingMatrix(hourly_df)

    # Test existing indexes
    assert "2025-01-01 00:00:00" in matrix
    assert "2025-01-01 01:00:00" in matrix

    # Test non-existing index
    assert "2025-01-01 02:00:00" not in matrix
    assert "2025-01-01 05:00:00" not in matrix


def test_contains_with_datetime_object(hourly_df):
    """Test the __contains__ method with datetime object."""
    matrix = ForecastingMatrix(hourly_df)

    # Test existing indexes
    assert datetime(2025, 1, 1, 0, 0, 0) in matrix
    assert datetime(2025, 1, 1, 1, 0, 0) in matrix

    # Test non-existing index
    assert datetime(2025, 1, 1, 2, 0, 0) not in matrix
    assert datetime(2025, 1, 1, 5, 0, 0) not in matrix


def test_contains_with_pendulum_datetime(hourly_df):
    """Test the __contains__ method with pendulum DateTime object."""
    matrix = ForecastingMatrix(hourly_df)

    # Test existing indexes
    assert pendulum.DateTime(2025, 1, 1, 0, 0, 0) in matrix
    assert pendulum.DateTime(2025, 1, 1, 1, 0, 0) in matrix

    # Test non-existing index
    assert pendulum.DateTime(2025, 1, 1, 2, 0, 0) not in matrix
    assert pendulum.DateTime(2025, 1, 1, 5, 0, 0) not in matrix


def test_contains_with_custom_date_format():
    """Test __contains__ with custom date format."""
    custom_format = "YYYY-MM-DD HH:mm"
    df = pl.DataFrame(
        {
            "time": pl.datetime_range(
                start=datetime(2025, 1, 1, 0, 0, 0),
                end=datetime(2025, 1, 1, 4, 0, 0),
                interval="1h",
                time_unit="us",
                eager=True,
            ),
            "2025-01-01 00:00": [1, 2, 3, 4, 5],
            "2025-01-01 01:00": [6, 7, 8, 9, 10],
        }
    )
    matrix = ForecastingMatrix(df, date_format=custom_format)

    # Test with string in custom format
    assert "2025-01-01 00:00" in matrix
    assert "2025-01-01 01:00" in matrix
    assert "2025-01-01 02:00" not in matrix

    # Test with datetime object (should still work, converted to custom format)
    assert datetime(2025, 1, 1, 0, 0, 0) in matrix
    assert datetime(2025, 1, 1, 1, 0, 0) in matrix
    assert datetime(2025, 1, 1, 2, 0, 0) not in matrix


def test_get_timeseries(hourly_df):
    matrix = ForecastingMatrix(hourly_df)

    ts = matrix.select(datetime(2025, 1, 1, 0, 0, 0))

    assert isinstance(ts, Timeseries)
    assert ts.shape[0] == 5


def test_delete_timeseries(hourly_df):
    matrix = ForecastingMatrix(hourly_df)

    matrix.delete(datetime(2025, 1, 1, 0, 0, 0))

    assert "2025-01-01 00:00:00" not in matrix.indexes
    assert matrix.matrix.columns == ["time", "2025-01-01 01:00:00"]


def test_init_with_pandas_df():
    """Test initialization with a pandas DataFrame."""
    pd_df = pd.DataFrame(
        {
            "time": pd.date_range(
                start=datetime(2025, 1, 1, 0, 0, 0),
                end=datetime(2025, 1, 1, 4, 0, 0),
                freq="1h",
            ),
            "2025-01-01 00:00:00": [1, 2, 3, 4, 5],
            "2025-01-01 01:00:00": [6, 7, 8, 9, 10],
        }
    )
    matrix = ForecastingMatrix(pd_df)
    assert isinstance(matrix, ForecastingMatrix)
    assert matrix.indexes == ["2025-01-01 00:00:00", "2025-01-01 01:00:00"]


def test_repr(hourly_df):
    """Test the __repr__ method."""
    matrix = ForecastingMatrix(hourly_df)
    repr_str = repr(matrix)
    assert "Forecasting Matrix" in repr_str


def test_custom_date_format():
    """Test using a custom date format."""
    custom_format = "YYYY-MM-DD HH:mm"
    df = pl.DataFrame(
        {
            "time": pl.datetime_range(
                start=datetime(2025, 1, 1, 0, 0, 0),
                end=datetime(2025, 1, 1, 4, 0, 0),
                interval="1h",
                time_unit="us",
                eager=True,
            ),
            "2025-01-01 00:00": [1, 2, 3, 4, 5],
            "2025-01-01 01:00": [6, 7, 8, 9, 10],
        }
    )
    matrix = ForecastingMatrix(df, date_format=custom_format)
    assert matrix.date_format == custom_format
    assert matrix.indexes == ["2025-01-01 00:00", "2025-01-01 01:00"]

    # Test adding with custom format
    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 3, 0, 0),
                    datetime(2025, 1, 1, 7, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [11, 12, 13, 14, 15],
            }
        )
    )
    matrix.add(new_ts, "2025-01-01 02:00")
    assert "2025-01-01 02:00" in matrix.indexes


def test_custom_timezone():
    """Test using a custom timezone."""
    df = pl.DataFrame(
        {
            "time": pl.datetime_range(
                start=datetime(2025, 1, 1, 0, 0, 0),
                end=datetime(2025, 1, 1, 4, 0, 0),
                interval="1h",
                time_unit="us",
                eager=True,
            ),
            "2025-01-01 00:00:00": [1, 2, 3, 4, 5],
            "2025-01-01 01:00:00": [6, 7, 8, 9, 10],
        }
    )
    matrix = ForecastingMatrix(df, timezone="Europe/Paris")
    assert matrix.timezone == "Europe/Paris"


def test_from_file_csv(hourly_df):
    """Test loading from a CSV file."""
    with NamedTemporaryFile(suffix=".csv", delete=False) as temp_file:
        file_path = temp_file.name

    try:
        hourly_df.write_csv(file_path, separator=";")
        matrix = ForecastingMatrix.from_file(file_path, separator=";")
        assert isinstance(matrix, ForecastingMatrix)
        assert matrix.indexes == ["2025-01-01 00:00:00", "2025-01-01 01:00:00"]

        # Test with Path object
        path_obj = Path(file_path)
        matrix_from_path = ForecastingMatrix.from_file(path_obj, separator=";")
        assert isinstance(matrix_from_path, ForecastingMatrix)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


def test_from_file_parquet(hourly_df):
    """Test loading from a Parquet file."""
    with NamedTemporaryFile(suffix=".parquet", delete=False) as temp_file:
        file_path = temp_file.name

    try:
        hourly_df.write_parquet(file_path)
        matrix = ForecastingMatrix.from_file(file_path)
        assert isinstance(matrix, ForecastingMatrix)
        assert matrix.indexes == ["2025-01-01 00:00:00", "2025-01-01 01:00:00"]
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


def test_from_file_with_filters(filtered_df):
    """Test loading from a file with filters."""
    with NamedTemporaryFile(suffix=".csv", delete=False) as temp_file:
        file_path = temp_file.name

    try:
        filtered_df.write_csv(file_path, separator=";")
        matrix = ForecastingMatrix.from_file(file_path, filters=("scenario", "A"), separator=";")
        assert isinstance(matrix, ForecastingMatrix)
        assert "scenario" not in matrix.matrix.columns
        assert matrix.indexes == ["2025-01-01 00:00:00", "2025-01-01 01:00:00"]
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


def test_from_file_unsupported_extension():
    """Test loading from an unsupported file type."""
    with NamedTemporaryFile(suffix=".txt", delete=False) as temp_file:
        file_path = temp_file.name

    try:
        with pytest.raises(NotImplementedError):
            ForecastingMatrix.from_file(file_path)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


def test_add_with_dict(hourly_df):
    """Test adding timeseries with different data types."""
    matrix = ForecastingMatrix(hourly_df)

    # Test with dict
    dict_data = {
        "time": pl.datetime_range(
            datetime(2025, 1, 1, 3, 0, 0),
            datetime(2025, 1, 1, 7, 0, 0),
            "1h",
            time_unit="us",
            eager=True,
        ),
        "values": [11, 12, 13, 14, 15],
    }
    matrix.add(dict_data, datetime(2025, 1, 1, 2, 0, 0))
    assert "2025-01-01 02:00:00" in matrix.indexes


def test_add_pandas_df(hourly_df):
    matrix = ForecastingMatrix(hourly_df)

    # Test with pandas DataFrame
    pd_df = pd.DataFrame(
        {
            "time": pd.date_range(
                start=datetime(2025, 1, 1, 3, 0, 0),
                end=datetime(2025, 1, 1, 7, 0, 0),
                freq="1h",
            ),
            "values": [16, 17, 18, 19, 20],
        }
    )
    matrix.add(pd_df, "2025-01-01 03:00:00")
    assert "2025-01-01 03:00:00" in matrix.indexes


def test_add_duplicate_index(hourly_df):
    """Test adding a timeseries with a duplicate index raises error."""
    matrix = ForecastingMatrix(hourly_df)

    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 3, 0, 0),
                    datetime(2025, 1, 1, 7, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [11, 12, 13, 14, 15],
            }
        )
    )

    # Try to add with existing index
    with pytest.raises(KeyError, match="Index .* already exists in the matrix"):
        matrix.add(new_ts, "2025-01-01 00:00:00")


def test_add_with_datetime_object(hourly_df):
    """Test adding timeseries with datetime object as index."""
    matrix = ForecastingMatrix(hourly_df)

    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 3, 0, 0),
                    datetime(2025, 1, 1, 7, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [11, 12, 13, 14, 15],
            }
        )
    )

    # Add with datetime object
    dt_index = datetime(2025, 1, 1, 2, 0, 0)
    matrix.add(new_ts, dt_index)
    assert "2025-01-01 02:00:00" in matrix.indexes

    # Verify the matrix columns are properly sorted
    expected_columns = ["time", "2025-01-01 00:00:00", "2025-01-01 01:00:00", "2025-01-01 02:00:00"]
    assert matrix.matrix.columns == expected_columns


def test_add_with_pendulum_datetime(hourly_df):
    """Test adding timeseries with pendulum DateTime object as index."""
    matrix = ForecastingMatrix(hourly_df)

    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 3, 0, 0),
                    datetime(2025, 1, 1, 7, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [11, 12, 13, 14, 15],
            }
        )
    )

    # Add with pendulum datetime
    pdt_index = pendulum.DateTime(2025, 1, 1, 2, 30, 0)
    matrix.add(new_ts, pdt_index)
    assert "2025-01-01 02:30:00" in matrix.indexes


def test_get_timeseries_with_string_index(hourly_df):
    """Test getting a timeseries using a string index."""
    matrix = ForecastingMatrix(hourly_df)
    ts = matrix.select("2025-01-01 00:00:00")
    assert isinstance(ts, Timeseries)
    assert ts.dataframe.shape[0] == 5


def test_get_timeseries_invalid_index(hourly_df):
    """Test getting a timeseries with an invalid index."""
    matrix = ForecastingMatrix(hourly_df)
    with pytest.raises(KeyError):
        matrix.select("2025-01-01 05:00:00")


def test_delete_with_string_index(hourly_df):
    """Test deleting a timeseries using a string index."""
    matrix = ForecastingMatrix(hourly_df)
    matrix.delete("2025-01-01 00:00:00")
    assert "2025-01-01 00:00:00" not in matrix.indexes


def test_delete_invalid_index(hourly_df):
    """Test deleting a non-existent timeseries."""
    matrix = ForecastingMatrix(hourly_df)
    with pytest.raises(KeyError, match="No timeseries to delete"):
        matrix.delete("2025-01-01 05:00:00")


def test_delete_with_datetime_object(hourly_df):
    """Test deleting a timeseries using datetime object."""
    matrix = ForecastingMatrix(hourly_df)

    # Add a new timeseries first
    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 3, 0, 0),
                    datetime(2025, 1, 1, 7, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [11, 12, 13, 14, 15],
            }
        )
    )
    dt_index = datetime(2025, 1, 1, 2, 0, 0)
    matrix.add(new_ts, dt_index)
    assert "2025-01-01 02:00:00" in matrix.indexes

    # Delete using datetime object
    matrix.delete(dt_index)
    assert "2025-01-01 02:00:00" not in matrix.indexes

    # Verify indexes are re-sorted after deletion
    assert matrix.matrix.columns == ["time", "2025-01-01 00:00:00", "2025-01-01 01:00:00"]


def test_delete_with_pendulum_datetime(hourly_df):
    """Test deleting a timeseries using pendulum DateTime object."""
    matrix = ForecastingMatrix(hourly_df)

    # Add a new timeseries first
    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 3, 0, 0),
                    datetime(2025, 1, 1, 7, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [11, 12, 13, 14, 15],
            }
        )
    )
    pdt_index = pendulum.DateTime(2025, 1, 1, 2, 30, 0)
    matrix.add(new_ts, pdt_index)
    assert "2025-01-01 02:30:00" in matrix.indexes

    # Delete using pendulum datetime object
    matrix.delete(pdt_index)
    assert "2025-01-01 02:30:00" not in matrix.indexes


def test_replace_timeseries(hourly_df):
    """Test replacing a timeseries in the matrix."""
    matrix = ForecastingMatrix(hourly_df)

    # Original timeseries values
    original_ts = matrix.select("2025-01-01 00:00:00")
    assert original_ts.get_value(datetime(2025, 1, 1, 0, 0, 0)) == 1.0

    # Create replacement timeseries with different values
    replacement_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 0, 0, 0),
                    datetime(2025, 1, 1, 4, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [100, 200, 300, 400, 500],  # Different values
            }
        )
    )

    # Replace the timeseries
    matrix.replace("2025-01-01 00:00:00", replacement_ts)

    # Verify replacement
    replaced_ts = matrix.select("2025-01-01 00:00:00")
    assert replaced_ts.get_value(datetime(2025, 1, 1, 0, 0, 0)) == 100.0
    assert replaced_ts.get_value(datetime(2025, 1, 1, 1, 0, 0)) == 200.0

    # Verify indexes remain sorted
    assert matrix.indexes == ["2025-01-01 00:00:00", "2025-01-01 01:00:00"]


def test_replace_with_datetime_object(hourly_df):
    """Test replacing a timeseries using datetime object as index."""
    matrix = ForecastingMatrix(hourly_df)

    replacement_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 0, 0, 0),
                    datetime(2025, 1, 1, 4, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [999, 888, 777, 666, 555],
            }
        )
    )

    dt_index = datetime(2025, 1, 1, 0, 0, 0)
    matrix.replace(dt_index, replacement_ts)

    # Verify replacement
    replaced_ts = matrix.select(dt_index)
    assert replaced_ts.get_value(datetime(2025, 1, 1, 0, 0, 0)) == 999.0


def test_replace_with_different_data_types(hourly_df):
    """Test replacing with different data types (dict, pandas DataFrame)."""
    matrix = ForecastingMatrix(hourly_df)

    # Replace with dictionary
    dict_data = {
        "time": pl.datetime_range(
            datetime(2025, 1, 1, 0, 0, 0),
            datetime(2025, 1, 1, 4, 0, 0),
            "1h",
            time_unit="us",
            eager=True,
        ),
        "values": [50, 60, 70, 80, 90],
    }
    matrix.replace("2025-01-01 00:00:00", dict_data)

    replaced_ts = matrix.select("2025-01-01 00:00:00")
    assert replaced_ts.get_value(datetime(2025, 1, 1, 0, 0, 0)) == 50.0

    # Replace with pandas DataFrame
    pd_df = pd.DataFrame(
        {
            "time": pd.date_range(
                start=datetime(2025, 1, 1, 0, 0, 0),
                end=datetime(2025, 1, 1, 4, 0, 0),
                freq="1h",
            ),
            "values": [111, 222, 333, 444, 555],
        }
    )
    matrix.replace("2025-01-01 00:00:00", pd_df)

    replaced_ts = matrix.select("2025-01-01 00:00:00")
    assert replaced_ts.get_value(datetime(2025, 1, 1, 0, 0, 0)) == 111.0


def test_replace_nonexistent_index(hourly_df):
    """Test replacing a non-existent timeseries."""
    matrix = ForecastingMatrix(hourly_df)

    replacement_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 0, 0, 0),
                    datetime(2025, 1, 1, 4, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [100, 200, 300, 400, 500],
            }
        )
    )

    # Try to replace non-existent index - should raise KeyError during delete
    with pytest.raises(KeyError, match="No timeseries to delete"):
        matrix.replace("2025-01-01 05:00:00", replacement_ts)


def test_set_date_format(hourly_df):
    """Test setting a custom date format."""
    matrix = ForecastingMatrix(hourly_df)
    matrix.set_date_format("YYYY-MM-DD HH:mm")
    assert matrix.date_format == "YYYY-MM-DD HH:mm"
    assert matrix.indexes == ["2025-01-01 00:00", "2025-01-01 01:00"]


def test_lazy_forecasting_matrix():
    """Test the LazyForecastingMatrix class."""
    # Create a LazyFrame
    lazy_df = pl.DataFrame(
        {
            "time": pl.datetime_range(
                start=datetime(2025, 1, 1, 0, 0, 0),
                end=datetime(2025, 1, 1, 4, 0, 0),
                interval="1h",
                time_unit="us",
                eager=True,
            ),
            "2025-01-01 00:00:00": [1, 2, 3, 4, 5],
            "2025-01-01 01:00:00": [6, 7, 8, 9, 10],
        }
    ).lazy()

    # Create from LazyMatrix
    lazy_matrix = LazyMatrix(lazy_df)
    lazy_forecasting = LazyForecastingMatrix(lazy_matrix, timezone="UTC")
    assert isinstance(lazy_forecasting, LazyForecastingMatrix)

    # Test from Matrix
    matrix = ForecastingMatrix(lazy_df.collect())
    lazy_forecasting_from_matrix = LazyForecastingMatrix(matrix)
    assert isinstance(lazy_forecasting_from_matrix, LazyForecastingMatrix)

    # Test from LazyFrame
    lazy_forecasting_from_frame = LazyForecastingMatrix(lazy_df)
    assert isinstance(lazy_forecasting_from_frame, LazyForecastingMatrix)

    # Test representation
    repr_str = repr(lazy_forecasting)
    assert "LazyForecastingMatrix" in repr_str


def test_lazy_forecasting_matrix_collect(hourly_df):
    """Test the collect method of LazyForecastingMatrix."""
    lazy_df = hourly_df.lazy()
    lazy_forecasting = LazyForecastingMatrix(lazy_df)

    # Collect the lazy frame
    collected_df = lazy_forecasting.collect()

    # Check if the collected DataFrame is as expected
    assert isinstance(collected_df, ForecastingMatrix)
    assert collected_df.shape == (5, 3)


def test_lazy_forecasting_matrix_add(hourly_df):
    """Test adding timeseries to LazyForecastingMatrix."""
    lazy_df = hourly_df.lazy()
    lazy_forecasting = LazyForecastingMatrix(lazy_df)

    # Create new timeseries
    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 3, 0, 0),
                    datetime(2025, 1, 1, 7, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [11, 12, 13, 14, 15],
            }
        )
    )

    # Test adding with string index
    lazy_forecasting.add(new_ts, "2025-01-01 02:00:00")
    collected = lazy_forecasting.collect()
    assert "2025-01-01 02:00:00" in collected.indexes

    # Test adding with datetime object
    new_ts2 = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 4, 0, 0),
                    datetime(2025, 1, 1, 8, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [21, 22, 23, 24, 25],
            }
        )
    )
    dt_index = datetime(2025, 1, 1, 3, 0, 0)
    lazy_forecasting.add(new_ts2, dt_index)
    collected = lazy_forecasting.collect()
    assert "2025-01-01 03:00:00" in collected.indexes


def test_lazy_forecasting_matrix_delete(hourly_df):
    """Test deleting timeseries from LazyForecastingMatrix."""
    lazy_df = hourly_df.lazy()
    lazy_forecasting = LazyForecastingMatrix(lazy_df)

    # Delete with string index - only delete one scenario
    lazy_forecasting.delete("2025-01-01 00:00:00")
    collected = lazy_forecasting.collect()
    assert "2025-01-01 00:00:00" not in collected.indexes
    assert "2025-01-01 01:00:00" in collected.indexes
    assert len(collected.indexes) == 1

    # Verify we can still use the remaining scenario
    remaining_ts = collected.select("2025-01-01 01:00:00")
    assert remaining_ts.get_value(datetime(2025, 1, 1, 0, 0, 0)) == 6.0


def test_lazy_forecasting_matrix_delete_with_datetime():
    """Test deleting with datetime object on a fresh matrix."""
    df = pl.DataFrame(
        {
            "time": pl.datetime_range(
                start=datetime(2025, 1, 1, 0, 0, 0),
                end=datetime(2025, 1, 1, 4, 0, 0),
                interval="1h",
                time_unit="us",
                eager=True,
            ),
            "2025-01-01 00:00:00": [1, 2, 3, 4, 5],
            "2025-01-01 01:00:00": [6, 7, 8, 9, 10],
        }
    )
    lazy_forecasting = LazyForecastingMatrix(df.lazy())

    # Delete with datetime object
    dt_index = datetime(2025, 1, 1, 0, 0, 0)
    lazy_forecasting.delete(dt_index)
    collected = lazy_forecasting.collect()
    assert "2025-01-01 00:00:00" not in collected.indexes
    assert "2025-01-01 01:00:00" in collected.indexes


def test_lazy_forecasting_matrix_replace(hourly_df):
    """Test replacing timeseries in LazyForecastingMatrix."""
    lazy_df = hourly_df.lazy()
    lazy_forecasting = LazyForecastingMatrix(lazy_df)

    # Create replacement timeseries
    replacement_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 0, 0, 0),
                    datetime(2025, 1, 1, 4, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [100, 200, 300, 400, 500],
            }
        )
    )

    # Replace with string index
    lazy_forecasting.replace("2025-01-01 00:00:00", replacement_ts)
    collected = lazy_forecasting.collect()
    replaced_ts = collected.select("2025-01-01 00:00:00")
    assert replaced_ts.get_value(datetime(2025, 1, 1, 0, 0, 0)) == 100.0

    # Replace with datetime object
    replacement_ts2 = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 1, 0, 0),
                    datetime(2025, 1, 1, 5, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [999, 888, 777, 666, 555],
            }
        )
    )
    dt_index = datetime(2025, 1, 1, 1, 0, 0)
    lazy_forecasting.replace(dt_index, replacement_ts2)
    collected = lazy_forecasting.collect()
    replaced_ts = collected.select(dt_index)
    assert replaced_ts.get_value(datetime(2025, 1, 1, 1, 0, 0)) == 999.0


def test_lazy_forecasting_matrix_contains_with_string_index(hourly_df):
    """Test the __contains__ method with string index on LazyForecastingMatrix."""
    lazy_df = hourly_df.lazy()
    lazy_forecasting = LazyForecastingMatrix(lazy_df)

    # Test existing indexes
    assert "2025-01-01 00:00:00" in lazy_forecasting
    assert "2025-01-01 01:00:00" in lazy_forecasting

    # Test non-existing index
    assert "2025-01-01 02:00:00" not in lazy_forecasting
    assert "2025-01-01 05:00:00" not in lazy_forecasting


def test_lazy_forecasting_matrix_contains_with_datetime_object(hourly_df):
    """Test the __contains__ method with datetime object on LazyForecastingMatrix."""
    lazy_df = hourly_df.lazy()
    lazy_forecasting = LazyForecastingMatrix(lazy_df)

    # Test existing indexes
    assert datetime(2025, 1, 1, 0, 0, 0) in lazy_forecasting
    assert datetime(2025, 1, 1, 1, 0, 0) in lazy_forecasting

    # Test non-existing index
    assert datetime(2025, 1, 1, 2, 0, 0) not in lazy_forecasting
    assert datetime(2025, 1, 1, 5, 0, 0) not in lazy_forecasting


def test_lazy_forecasting_matrix_contains_with_pendulum_datetime(hourly_df):
    """Test the __contains__ method with pendulum DateTime object on LazyForecastingMatrix."""
    lazy_df = hourly_df.lazy()
    lazy_forecasting = LazyForecastingMatrix(lazy_df)

    # Test existing indexes
    assert pendulum.DateTime(2025, 1, 1, 0, 0, 0) in lazy_forecasting
    assert pendulum.DateTime(2025, 1, 1, 1, 0, 0) in lazy_forecasting

    # Test non-existing index
    assert pendulum.DateTime(2025, 1, 1, 2, 0, 0) not in lazy_forecasting
    assert pendulum.DateTime(2025, 1, 1, 5, 0, 0) not in lazy_forecasting


def test_lazy_forecasting_matrix_contains_after_add(hourly_df):
    """Test __contains__ after adding new timeseries to LazyForecastingMatrix."""
    lazy_df = hourly_df.lazy()
    lazy_forecasting = LazyForecastingMatrix(lazy_df)

    # Initially not present
    assert "2025-01-01 02:00:00" not in lazy_forecasting

    # Add a new timeseries
    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 3, 0, 0),
                    datetime(2025, 1, 1, 7, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [11, 12, 13, 14, 15],
            }
        )
    )
    lazy_forecasting.add(new_ts, datetime(2025, 1, 1, 2, 0, 0))

    # Now it should be present
    assert "2025-01-01 02:00:00" in lazy_forecasting
    assert datetime(2025, 1, 1, 2, 0, 0) in lazy_forecasting


def test_lazy_forecasting_matrix_get_forecast(hourly_df):
    """Test get_forecast method in LazyForecastingMatrix."""
    lazy_df = hourly_df.lazy()
    lazy_forecasting = LazyForecastingMatrix(lazy_df)

    # Add another forecast
    new_ts = Timeseries(
        pl.DataFrame(
            {
                "time": pl.datetime_range(
                    datetime(2025, 1, 1, 2, 0, 0),
                    datetime(2025, 1, 1, 6, 0, 0),
                    "1h",
                    time_unit="us",
                    eager=True,
                ),
                "values": [11, 12, 13, 14, 15],
            }
        )
    )
    lazy_forecasting.add(new_ts, "2025-01-01 01:30:00")

    # Test get_forecast - should collect and delegate to ForecastingMatrix
    # Use execution_date that allows both initial forecasts to be available
    execution_date = datetime(2025, 1, 1, 2, 0, 0)  # After both 00:00:00 and 01:00:00 forecasts
    start_date = datetime(2025, 1, 1, 0, 0, 0)
    end_date = datetime(2025, 1, 1, 3, 0, 0)

    forecast = lazy_forecasting.get_forecast(execution_date, start_date, end_date)
    assert isinstance(forecast, Timeseries)
    # Should use the most recent forecast available at execution_date
    # Original forecast at 00:00:00 has values [1,2,3,4,5] for times [00:00, 01:00, 02:00, 03:00, 04:00]
    # Original forecast at 01:00:00 has values [6,7,8,9,10] for times [00:00, 01:00, 02:00, 03:00, 04:00]
    # Added forecast at 01:30:00 has values [11,12,13,14,15] for times [02:00, 03:00, 04:00, 05:00, 06:00]
    # At execution_date 02:00:00, forecasts at 00:00:00, 01:00:00, and 01:30:00 are all available
    # get_forecast should use newest available forecast for each time point
    assert forecast.get_value(datetime(2025, 1, 1, 0, 0, 0)) == 6.0  # From 01:00:00 forecast (newer than 00:00:00)
    assert forecast.get_value(datetime(2025, 1, 1, 1, 0, 0)) == 7.0  # From 01:00:00 forecast
    assert forecast.get_value(datetime(2025, 1, 1, 2, 0, 0)) == 11.0  # From 01:30:00 forecast (newest available)


class TestGetForecast:
    @staticmethod
    def retrieve_ts(start: int, freq: str, values: list[int]):
        return Timeseries.from_values(pendulum.datetime(2025, 1, 1, start, 0, 0), freq, values)

    @pytest.fixture
    def ts_1_hour_at_0_with_8_values(self):
        return TestGetForecast.retrieve_ts(0, "1h", [1, 2, 3, 4, 5, 6, 7, 8])

    @pytest.fixture
    def ts_30_min_at_0_with_4_values(self):
        return TestGetForecast.retrieve_ts(0, "30m", [1, 2, 3, 4])

    @pytest.fixture
    def ts_30_min_at_1_with_4_values(self):
        return TestGetForecast.retrieve_ts(1, "30m", [11, 12, 13, 14])

    @pytest.fixture
    def ts_15_min_at_1_with_8_values(self):
        return TestGetForecast.retrieve_ts(1, "15m", [11, 12, 13, 14, 15, 16, 17, 18])

    @pytest.fixture
    def ts_30_min_at_2_with_4_values(self):
        return TestGetForecast.retrieve_ts(2, "30m", [21, 22, 23, 24])

    def test_with_one_ts(self, ts_30_min_at_0_with_4_values):
        forecast_matrix = ForecastingMatrix()
        forecast_matrix.add(ts_30_min_at_0_with_4_values, pendulum.DateTime(2025, 1, 1))

        start_date = pendulum.datetime(2025, 1, 1, 0)
        end_date = pendulum.datetime(2025, 1, 1, 1, 30)
        execution_date = pendulum.datetime(2025, 1, 1)
        expected_step = pendulum.duration(minutes=30)

        expected_result = pl.DataFrame(
            {
                "time": [start_date + i * expected_step for i in range((end_date - start_date) // expected_step + 1)],
                "value": [1, 2, 3, 4],
            }
        )

        result = forecast_matrix.get_forecast(execution_date, start_date, end_date, expected_step)

        assert result.dataframe.equals(expected_result)

    def test_with_one_ts_end_date_inferior(self, ts_30_min_at_0_with_4_values):
        forecast_matrix = ForecastingMatrix()
        forecast_matrix.add(ts_30_min_at_0_with_4_values, pendulum.DateTime(2025, 1, 1))

        start_date = pendulum.datetime(2025, 1, 1, 0)
        end_date = pendulum.datetime(2025, 1, 1, 2, 30)
        execution_date = pendulum.datetime(2025, 1, 1)
        expected_step = pendulum.duration(minutes=30)

        expected_end_date = pendulum.datetime(2025, 1, 1, 1, 30)
        expected_result = pl.DataFrame(
            {
                "time": [
                    start_date + i * expected_step for i in range((expected_end_date - start_date) // expected_step + 1)
                ],
                "value": [1, 2, 3, 4],
            }
        )
        result = forecast_matrix.get_forecast(execution_date, start_date, end_date, expected_step)

        assert result.dataframe.equals(expected_result)
        with pytest.raises(KeyError):
            result.get_value(pendulum.datetime(2025, 1, 1, 2, 30))

    def test_with_one_ts_start_date_superior(self, ts_30_min_at_0_with_4_values):
        forecast_matrix = ForecastingMatrix()
        forecast_matrix.add(ts_30_min_at_0_with_4_values, pendulum.DateTime(2025, 1, 1))

        start_date = pendulum.datetime(2024, 12, 31, 23)
        end_date = pendulum.datetime(2025, 1, 1, 1, 30)
        execution_date = pendulum.datetime(2025, 1, 1)

        result = forecast_matrix.get_forecast(execution_date, start_date, end_date)
        expected_start_date = pendulum.datetime(2025, 1, 1, 0, 0)
        expected_step = pendulum.duration(minutes=30)

        expected_end_date = pendulum.datetime(2025, 1, 1, 1, 30)
        expected_result = pl.DataFrame(
            {
                "time": [
                    expected_start_date + i * expected_step
                    for i in range((expected_end_date - expected_start_date) // expected_step + 1)
                ],
                "value": [1, 2, 3, 4],
            }
        )
        assert result.dataframe.equals(expected_result)
        with pytest.raises(KeyError):
            result.get_value(pendulum.datetime(2025, 1, 1, 2, 30))

    def test_with_one_ts_and_lower_frequency(self, ts_30_min_at_0_with_4_values):
        forecast_matrix = ForecastingMatrix()
        forecast_matrix.add(ts_30_min_at_0_with_4_values, pendulum.DateTime(2025, 1, 1))

        start_date = pendulum.datetime(2025, 1, 1, 0)
        end_date = pendulum.datetime(2025, 1, 1, 1, 30)
        execution_date = pendulum.datetime(2025, 1, 1)
        expected_step = pendulum.duration(minutes=15)
        expected_times = [start_date + i * expected_step for i in range((end_date - start_date) // expected_step + 1)]

        expected_result = pl.DataFrame(
            {
                "time": expected_times,
                "value": [1, 1, 2, 2, 3, 3, 4],
            }
        )
        result = forecast_matrix.get_forecast(execution_date, start_date, end_date, expected_step)

        assert result.dataframe.equals(expected_result)

    def test_with_one_ts_and_lower_frequency_and_too_short(self, ts_30_min_at_0_with_4_values):
        forecast_matrix = ForecastingMatrix()
        forecast_matrix.add(ts_30_min_at_0_with_4_values, pendulum.DateTime(2025, 1, 1))

        start_date = pendulum.datetime(2025, 1, 1, 0, 30)
        end_date = pendulum.datetime(2025, 1, 1, 2, 30)
        execution_date = pendulum.datetime(2025, 1, 1)

        expected_step = pendulum.duration(minutes=15)
        expected_end_date = pendulum.datetime(2025, 1, 1, 1, 45)
        expected_times = [
            start_date + i * expected_step for i in range((expected_end_date - start_date) // expected_step + 1)
        ]

        result = forecast_matrix.get_forecast(execution_date, start_date, end_date, expected_step)

        expected_result = pl.DataFrame(
            {
                "time": expected_times,
                "value": [2, 2, 3, 3, 4, 4],
            }
        )
        assert result.dataframe.equals(expected_result)

    def test_with_two_ts_with_different_frequency_first_one_is_longer(
        self,
        ts_1_hour_at_0_with_8_values,
        ts_15_min_at_1_with_8_values,
    ):
        forecast_matrix = ForecastingMatrix()
        forecast_matrix.add(ts_1_hour_at_0_with_8_values, pendulum.DateTime(2025, 1, 1))
        forecast_matrix.add(ts_15_min_at_1_with_8_values, pendulum.DateTime(2025, 1, 1, 1))

        start_date = pendulum.datetime(2025, 1, 1, 0, 30)
        end_date = pendulum.datetime(2025, 1, 1, 3, 30)
        execution_date = pendulum.datetime(2025, 1, 1, 1)
        expected_step = pendulum.duration(minutes=30)
        expected_times = [start_date + i * expected_step for i in range((end_date - start_date) // expected_step + 1)]
        expected_result = pl.DataFrame(
            {
                "time": expected_times,
                "value": [1, 11, 13, 15, 17, 4, 4],
            }
        )

        result = forecast_matrix.get_forecast(execution_date, start_date, end_date, expected_step)

        assert result.dataframe.equals(expected_result)

    def test_get_forecast(
        self,
        ts_30_min_at_0_with_4_values,
        ts_30_min_at_1_with_4_values,
        ts_30_min_at_2_with_4_values,
    ):
        forecast_matrix = ForecastingMatrix()
        forecast_matrix.add(ts_30_min_at_0_with_4_values, pendulum.DateTime(2025, 1, 1))
        forecast_matrix.add(ts_30_min_at_1_with_4_values, pendulum.DateTime(2025, 1, 1, 1))
        forecast_matrix.add(ts_30_min_at_2_with_4_values, pendulum.DateTime(2025, 1, 1, 2))

        start_date = pendulum.datetime(2025, 1, 1, 0, 30)
        end_date = pendulum.datetime(2025, 1, 1, 3, 30)
        execution_date = pendulum.datetime(2025, 1, 1, 2)
        expected_step = pendulum.duration(minutes=30)

        expected_result = pl.DataFrame(
            {
                "time": [start_date + i * expected_step for i in range((end_date - start_date) // expected_step + 1)],
                "value": [2.0, 11.0, 12.0, 21.0, 22.0, 23.0, 24.0],
            }
        )
        result = forecast_matrix.get_forecast(execution_date, start_date, end_date, expected_step)

        assert result.dataframe.equals(expected_result)

    def test_get_forecast_with_different_frequency(
        self,
        ts_30_min_at_0_with_4_values,
        ts_15_min_at_1_with_8_values,
        ts_30_min_at_2_with_4_values,
    ):
        forecast_matrix = ForecastingMatrix()
        forecast_matrix.add(ts_30_min_at_0_with_4_values, pendulum.DateTime(2025, 1, 1))
        forecast_matrix.add(ts_15_min_at_1_with_8_values, pendulum.DateTime(2025, 1, 1, 1))
        forecast_matrix.add(ts_30_min_at_2_with_4_values, pendulum.DateTime(2025, 1, 1, 2))

        start_date = pendulum.datetime(2025, 1, 1, 0, 30)
        end_date = pendulum.datetime(2025, 1, 1, 3, 30)
        execution_date = pendulum.datetime(2025, 1, 1, 2)
        expected_step = pendulum.duration(minutes=15)
        expected_result = pl.DataFrame(
            {
                "time": [start_date + i * expected_step for i in range((end_date - start_date) // expected_step + 1)],
                "value": [
                    2.0,
                    2.0,
                    11.0,
                    12.0,
                    13.0,
                    14.0,
                    21.0,
                    21.0,
                    22.0,
                    22.0,
                    23.0,
                    23.0,
                    24.0,
                ],
            }
        )

        result = forecast_matrix.get_forecast(execution_date, start_date, end_date, expected_step)

        assert result.dataframe.equals(expected_result)

    def test_get_forecast_with_fist_one_longer(self, ts_1_hour_at_0_with_8_values, ts_30_min_at_2_with_4_values):
        forecast_matrix = ForecastingMatrix()
        forecast_matrix.add(ts_1_hour_at_0_with_8_values, pendulum.DateTime(2025, 1, 1))
        forecast_matrix.add(ts_30_min_at_2_with_4_values, pendulum.DateTime(2025, 1, 1, 2))

        start_date = pendulum.datetime(2025, 1, 1, 0, 30)
        end_date = pendulum.datetime(2025, 1, 1, 4, 30)
        execution_date = pendulum.datetime(2025, 1, 1, 2)
        expected_step = pendulum.duration(minutes=30)
        expected_result = pl.DataFrame(
            {
                "time": [start_date + i * expected_step for i in range((end_date - start_date) // expected_step + 1)],
                "value": [1.0, 2.0, 2.0, 21, 22, 23, 24, 5.0, 5.0],
            }
        )

        result = forecast_matrix.get_forecast(execution_date, start_date, end_date, expected_step)

        assert result.dataframe.equals(expected_result)
