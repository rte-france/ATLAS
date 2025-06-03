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
            "01_01_2025 00:00:00": [1, 2, 3, 4, 5],
            "01_01_2025 01:00:00": [6, 7, 8, 9, 10],
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
            "01_01_2025 00:00:00": [1, 2, 3, 4, 5],
            "01_01_2025 01:00:00": [6, 7, 8, 9, 10],
        }
    )


def test_init_and_sorting(hourly_df):
    matrix = ForecastingMatrix(hourly_df)
    assert isinstance(matrix, ForecastingMatrix)
    assert matrix.indexes == ["01_01_2025 00:00:00", "01_01_2025 01:00:00"]
    assert matrix.matrix.columns == ["time", "01_01_2025 00:00:00", "01_01_2025 01:00:00"]


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
    assert "01_01_2025 02:00:00" in matrix.indexes
    assert matrix.matrix.columns == [
        "time",
        "01_01_2025 00:00:00",
        "01_01_2025 01:00:00",
        "01_01_2025 02:00:00",
    ]

    matrix.add(new_ts, "01_01_2025 03:00:00")

    # Check new index exists, sorted
    assert "01_01_2025 03:00:00" in matrix.indexes
    assert matrix.matrix.columns == [
        "time",
        "01_01_2025 00:00:00",
        "01_01_2025 01:00:00",
        "01_01_2025 02:00:00",
        "01_01_2025 03:00:00",
    ]


def test_get_timeseries(hourly_df):
    matrix = ForecastingMatrix(hourly_df)

    ts = matrix.select(datetime(2025, 1, 1, 0, 0, 0))

    assert isinstance(ts, Timeseries)
    assert ts.shape[0] == 5


def test_delete_timeseries(hourly_df):
    matrix = ForecastingMatrix(hourly_df)

    matrix.delete(datetime(2025, 1, 1, 0, 0, 0))

    assert "01_01_2025 00:00:00" not in matrix.indexes
    assert matrix.matrix.columns == ["time", "01_01_2025 01:00:00"]


def test_init_with_pandas_df():
    """Test initialization with a pandas DataFrame."""
    pd_df = pd.DataFrame(
        {
            "time": pd.date_range(
                start=datetime(2025, 1, 1, 0, 0, 0),
                end=datetime(2025, 1, 1, 4, 0, 0),
                freq="1h",
            ),
            "01_01_2025 00:00:00": [1, 2, 3, 4, 5],
            "01_01_2025 01:00:00": [6, 7, 8, 9, 10],
        }
    )
    matrix = ForecastingMatrix(pd_df)
    assert isinstance(matrix, ForecastingMatrix)
    assert matrix.indexes == ["01_01_2025 00:00:00", "01_01_2025 01:00:00"]


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
            "01_01_2025 00:00:00": [1, 2, 3, 4, 5],
            "01_01_2025 01:00:00": [6, 7, 8, 9, 10],
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
        assert matrix.indexes == ["01_01_2025 00:00:00", "01_01_2025 01:00:00"]

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
        assert matrix.indexes == ["01_01_2025 00:00:00", "01_01_2025 01:00:00"]
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
        assert matrix.indexes == ["01_01_2025 00:00:00", "01_01_2025 01:00:00"]
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
    assert "01_01_2025 02:00:00" in matrix.indexes


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
    matrix.add(pd_df, "01_01_2025 03:00:00")
    assert "01_01_2025 03:00:00" in matrix.indexes


def test_get_timeseries_with_string_index(hourly_df):
    """Test getting a timeseries using a string index."""
    matrix = ForecastingMatrix(hourly_df)
    ts = matrix.select("01_01_2025 00:00:00")
    assert isinstance(ts, Timeseries)
    assert ts.to_frame().shape[0] == 5


def test_get_timeseries_invalid_index(hourly_df):
    """Test getting a timeseries with an invalid index."""
    matrix = ForecastingMatrix(hourly_df)
    with pytest.raises(KeyError):
        matrix.select("01_01_2025 05:00:00")


def test_delete_with_string_index(hourly_df):
    """Test deleting a timeseries using a string index."""
    matrix = ForecastingMatrix(hourly_df)
    matrix.delete("01_01_2025 00:00:00")
    assert "01_01_2025 00:00:00" not in matrix.indexes


def test_delete_invalid_index(hourly_df):
    """Test deleting a non-existent timeseries."""
    matrix = ForecastingMatrix(hourly_df)
    with pytest.raises(KeyError):
        matrix.delete("01_01_2025 05:00:00")


def test_set_date_format(hourly_df):
    """Test setting a custom date format."""
    matrix = ForecastingMatrix(hourly_df)
    matrix.set_date_format("YYYY-MM-DD HH:mm")
    assert matrix.date_format == "YYYY-MM-DD HH:mm"
    assert matrix.index == ["2025-01-01 00:00", "2025-01-01 01:00"]


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
            "01_01_2025 00:00:00": [1, 2, 3, 4, 5],
            "01_01_2025 01:00:00": [6, 7, 8, 9, 10],
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


class TestGetForecast:
    @staticmethod
    def retrieve_ts(start: int, freq: str, values: list[int]):
        return Timeseries.from_args(pendulum.datetime(2025, 1, 1, start, 0, 0), freq, values)

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

        result = forecast_matrix.get_forecast(execution_date, start_date, end_date)
        expected_step = pendulum.duration(minutes=30)

        expected_result = pl.DataFrame(
            {
                "time": [start_date + i * expected_step for i in range((end_date - start_date) // expected_step + 1)],
                "value": [2.0, 11.0, 12.0, 21.0, 22.0, 23.0, 24.0],
            }
        )
        assert result.to_frame().equals(expected_result)

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

        result = forecast_matrix.get_forecast(execution_date, start_date, end_date)
        expected_step = pendulum.duration(minutes=15)
        expected_result = pl.DataFrame(
            {
                "time": [start_date + i * expected_step for i in range((end_date - start_date) // expected_step + 1)],
                "value": [
                    2.0,
                    2.5,
                    11.0,
                    12.0,
                    13.0,
                    14.0,
                    21.0,
                    21.5,
                    22.0,
                    22.5,
                    23.0,
                    23.5,
                    24.0,
                ],
            }
        )
        assert result.to_frame().equals(expected_result)

    def test_get_forecast_with_fist_one_longer(self, ts_1_hour_at_0_with_8_values, ts_30_min_at_2_with_4_values):
        forecast_matrix = ForecastingMatrix()
        forecast_matrix.add(ts_1_hour_at_0_with_8_values, pendulum.DateTime(2025, 1, 1))
        forecast_matrix.add(ts_30_min_at_2_with_4_values, pendulum.DateTime(2025, 1, 1, 2))

        start_date = pendulum.datetime(2025, 1, 1, 0, 30)
        end_date = pendulum.datetime(2025, 1, 1, 4, 30)
        execution_date = pendulum.datetime(2025, 1, 1, 2)

        result = forecast_matrix.get_forecast(execution_date, start_date, end_date)
        expected_step = pendulum.duration(minutes=30)
        expected_result = pl.DataFrame(
            {
                "time": [start_date + i * expected_step for i in range((end_date - start_date) // expected_step + 1)],
                "value": [1.5, 2.0, 2.5, 21, 22, 23, 24, 5.0, 5.5],
            }
        )
        assert result.to_frame().equals(expected_result)
