"""
Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ForecastingMatrix
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import polars as pl

from atlas.math.matrix import Matrix
from atlas.math.timeseries import Timeseries


class ForecastingMatrix(Matrix):
    """
    Stores Timeseries objects indexed by datetime, with access and forecasting utilities.

    Inherits from `Matrix[datetime]` and provides additional methods for forecasting
    reconstruction from past or future available timeseries.
    """

    def __init__(
        self,
        matrix: pl.DataFrame | pd.DataFrame,
        timezone: str = "UTC",
        date_format: str = "%d_%m_%Y %H:%M:%S",
    ):
        """
        Initialize a ForecastingMatrix.

        :param name: Name of the matrix.
        :type name: str
        :param forecasting_dates: List of forecasting dates used as indexes.
        :type forecasting_dates: list[datetime]
        :param timeseries: List of corresponding Timeseries objects.
        :type timeseries: list[Timeseries]
        """
        super().__init__(matrix, timezone=timezone)
        self._sort_indexes(date_format=date_format)

        self.date_format: str = date_format

    @classmethod
    def from_file(cls, file_path: str | Path) -> ForecastingMatrix:
        """
        Load a ForecastingMatrix from a file.

        :param file_path: Path to the file (CSV or Parquet).
        :type file_path: str | Path
        :return: A ForecastingMatrix object.
        :rtype: ForecastingMatrix
        """
        if isinstance(file_path, str):
            file_path = Path(file_path)
        if file_path.suffix == ".csv":
            matrix = pl.read_csv(file_path)
        elif file_path.suffix == ".parquet":
            matrix = pl.read_parquet(file_path)
        return cls(matrix)

    def _sort_indexes(self, date_format: str = "%d_%m_%Y %H:%M:%S") -> None:
        """Sort the internal mapping of timeseries by datetime keys."""
        indexes_sorted = (
            pl.DataFrame({"indexes": self.indexes})
            .with_columns(pl.col("indexes").str.strptime(pl.Datetime(time_unit="us"), date_format, strict=False))
            .sort("indexes")
            .with_columns(pl.col("indexes").dt.strftime(date_format))
            .to_series()
            .to_list()
        )

        self.matrix = self.matrix.select("time", *indexes_sorted).sort("time")
        self.indexes = indexes_sorted

    def add(
        self,
        index: datetime,
        timeseries: Timeseries | pl.DataFrame | pd.DataFrame | dict[str, list],
    ) -> None:
        """
        Add a Timeseries to the matrix and keep indexes sorted.

        :param index: Index key.
        :type index: datetime
        :param timeseries: Timeseries to add.
        :type timeseries: Timeseries | pl.DataFrame | pd.DataFrame | dict[str, list]
        """
        super().add(index, timeseries)
        self._sort_indexes()

    def extract(self, index: datetime, start_date: datetime, end_date: datetime) -> Timeseries:
        """
        Extract a portion of a Timeseries at a specific forecast date.

        :param index: Forecasting datetime from which to extract.
        :type index: datetime
        :param start_date: Start of the extraction window.
        :type start_date: datetime
        :param end_date: End of the extraction window.
        :type end_date: datetime
        :return: A sliced Timeseries from the specified index.
        :rtype: Timeseries
        """
        ts = self.get_timeseries(index)
        return ts.filter([start_date, end_date])

    def get_timeseries(self, index: str | datetime, date_format="%d_%m_%Y %H:%M:%S") -> Timeseries:
        """
        Retrieve a timeseries by index.

        :param index: Index key.
        :type index: Index
        :raises KeyError: If the index is not found.
        :return: The Timeseries object.
        :rtype: Timeseries
        """
        dt: str = (
            datetime.strptime(index, date_format)  # noqa: DTZ007
            if isinstance(index, str)
            else index
        ).strftime(self.date_format)

        return super().__getitem__(dt)

    def delete(self, index: str | datetime) -> None:
        """
        Delete a timeseries by index.

        :param index: Index key.
        :type index: Index
        :raises KeyError: If index is not found.
        """
        dt: str = (
            datetime.strptime(index, self.date_format)  # noqa: DTZ007
            if isinstance(index, str)
            else index
        ).strftime(self.date_format)

        super().delete(dt)

        self._sort_indexes()

    # def get_forecast(
    #     self,
    #     ref_date: datetime,
    #     from_date: datetime,
    #     to_date: datetime,
    # ) -> Timeseries:
    #     """
    #     Construct a forecast by merging historical data up to a reference date.

    #     Builds a Timeseries by merging slices from all available forecasts
    #     that occurred **before or on** `ref_date`, in reverse order. Stops when the
    #     full range `[from_date, to_date]` is covered.

    #     :param ref_date: Reference datetime to stop looking backward.
    #     :type ref_date: datetime
    #     :param from_date: Start of the desired forecast window.
    #     :type from_date: datetime
    #     :param to_date: End of the desired forecast window.
    #     :type to_date: datetime
    #     :return: A reconstructed forecast as a Timeseries.
    #     :rtype: Timeseries
    #     """
    #     result = Timeseries("unknown", TimeSeriesInterpolation.CONSTANT, "", [], [])

    #     indexes_to_check = [d for d in self.indexes if d <= ref_date]
    #     for date in reversed(indexes_to_check):
    #         result = result.merge(self.timeseries_map[date].slice(from_date, to_date))
    #         if from_date in result.series.index and to_date in result.series.index:
    #             return result
    #     return result
