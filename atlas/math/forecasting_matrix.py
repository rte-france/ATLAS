"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ForecastingMatrix
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pendulum
import polars as pl

from atlas.math.lazy_matrix import LazyMatrix
from atlas.math.matrix import Matrix
from atlas.math.timeseries import Timeseries
from atlas.timing import pendulum_to_datetime

if TYPE_CHECKING:
    import pandas as pd


class ForecastingMatrix(Matrix):
    """
    A specialized matrix for handling forecasted timeseries data.

    Each column in the matrix corresponds to a forecast generated at a specific
    datetime, stored as a string with a configurable format. Internally, the
    matrix ensures columns are sorted chronologically by their forecast datetime.

    Inherits from:
        Matrix: Core matrix functionality with timeseries support.
    """

    def __init__(
        self,
        matrix: pl.DataFrame | pd.DataFrame,
        timezone: str = "UTC",
        date_format: str = "DD_MM_YYYY HH:mm:ss",
    ) -> None:
        """
        Initialize a ForecastingMatrix with a matrix of forecasted timeseries.

        :param matrix: A DataFrame where each column (except "time") represents a forecast.
        :type matrix: pl.DataFrame | pd.DataFrame
        :param timezone: Timezone of the timeseries data.
        :type timezone: str
        :param date_format: Format used for parsing and displaying datetime indexes.
        :type date_format: str
        """
        super().__init__(matrix, timezone=timezone)

        self.date_format: str = date_format
        self._sort_indexes()

    def __repr__(self):
        """Provide a string representation of the Matrix object."""
        return f"Forecasting Matrix : {self.matrix}"

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        separator: str = ";",
        date_format: str = "DD_MM_YYYY HH:mm:ss",
    ) -> ForecastingMatrix:
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
            matrix = pl.read_csv(file_path, try_parse_dates=True, separator=separator)
        elif file_path.suffix == ".parquet":
            matrix = pl.read_parquet(file_path)
        return cls(matrix, timezone, date_format)

    def _sort_indexes(self) -> None:
        """
        Sort the forecast matrix columns based on their datetime indexes.

        Columns are expected to be named using a specific datetime format.
        This method parses, sorts, and reorders the matrix accordingly.

        :param date_format: Format used to parse datetime from index names.
        :type date_format: str
        """
        indexes_sorted = (
            pl.DataFrame({"indexes": self.indexes})
            .with_columns(
                pl.col("indexes").str.strptime(
                    pl.Datetime(time_unit="us"),
                    pendulum_to_datetime(self.date_format),
                    strict=False,
                )
            )
            .sort("indexes")
            .with_columns(pl.col("indexes").dt.strftime(pendulum_to_datetime(self.date_format)))
            .to_series()
            .to_list()
        )

        self.matrix = self.matrix.select("time", *indexes_sorted).sort("time")
        self.indexes = indexes_sorted

    def add(
        self,
        timeseries: Timeseries | pl.DataFrame | pd.DataFrame | dict[str, list],
        index: str | datetime,
    ) -> None:
        """
        Add a Timeseries to the matrix and keep indexes sorted.

        :param timeseries: Timeseries data to add.
        :type timeseries: Timeseries | pl.DataFrame | pd.DataFrame | dict[str, list]
        :param index: Datetime key for the new forecast.
        :type index: str | datetime
        """
        if isinstance(index, str):
            dt: str = pendulum.from_format(index, self.date_format).format(self.date_format)
        else:
            dt: str = pendulum.instance(index).format(self.date_format)  # type: ignore[no-redef]

        super().add(timeseries, dt)
        self._sort_indexes()

    def get_timeseries(
        self,
        index: str | datetime,
    ) -> Timeseries:
        """
        Retrieve a timeseries by index.

        :param index: Forecast generation datetime (as string or datetime object).
        :type index: str | datetime
        :param date_format: Date format if the index is a string.
        :type date_format: str
        :raises KeyError: If the specified index is not found.
        :return: The corresponding Timeseries object.
        :rtype: Timeseries
        """
        dt: str = (
            pendulum.from_format(index, self.date_format) if isinstance(index, str) else pendulum.instance(index)
        ).format(self.date_format)

        return Timeseries(super().__getitem__(dt))

    def delete(self, index: str | datetime) -> None:
        """
        Delete a timeseries by index.

        :param index: Forecast generation datetime (as string or datetime object).
        :type index: str | datetime
        :raises KeyError: If the index does not exist in the matrix.
        """
        dt: str = (
            pendulum.from_format(index, self.date_format) if isinstance(index, str) else pendulum.instance(index)
        ).format(self.date_format)

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


class LazyForecastingMatrix(LazyMatrix):
    """Stores Timeseries objects lazily by scenario name, with access and deletion by name."""

    def __init__(self, matrix: LazyMatrix | pl.LazyFrame | Matrix, timezone: str = "UTC") -> None:
        super().__init__(matrix, timezone)

    def __repr__(self):
        """String representation of the matrix"""
        return f"LazyForecastingMatrix with schema : {self.matrix.collect_schema()}"
