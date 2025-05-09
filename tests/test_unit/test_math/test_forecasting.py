from datetime import datetime

import polars as pl
import pytest

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries


@pytest.fixture
def hourly_df():
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

    ts = matrix.get_timeseries(datetime(2025, 1, 1, 0, 0, 0))

    assert isinstance(ts, Timeseries)
    assert ts.get_data().shape[0] == 5  # 5 hourly points


def test_delete_timeseries(hourly_df):
    matrix = ForecastingMatrix(hourly_df)

    matrix.delete(datetime(2025, 1, 1, 0, 0, 0))

    assert "01_01_2025 00:00:00" not in matrix.indexes
    assert matrix.matrix.columns == ["time", "01_01_2025 01:00:00"]
