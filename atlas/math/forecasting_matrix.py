"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ForecastingMatrix
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pendulum
import polars as pl

from atlas.io_utils.utils import read_data_file
from atlas.math.lazy_matrix import LazyMatrix
from atlas.math.matrix import Matrix
from atlas.math.timeseries import Timeseries
from atlas.timing import (
    build_datetime,
    generate_datetimes,
    get_duration,
    get_lowest_frequency,
    infer_frequency,
    pendulum_to_datetime,
)

if TYPE_CHECKING:
    import pandas as pd


class ForecastingMatrix(Matrix):
    """
    A matrix structure for managing collections of forecast time series, indexed by forecast generation time.

    The ForecastingMatrix is designed to store and organize multiple time series forecasts,
    where each column (except for the "time" column) represents a forecast generated at a specific datetime.
    """

    def __init__(
        self,
        matrix: pl.DataFrame | pd.DataFrame | Matrix | None = None,
        timezone: str = "UTC",
        date_format: str = "YYYY-MM-DD HH:mm:ss",
    ) -> None:
        """
        :param matrix: A DataFrame where each column (except "time") represents a forecast.
        :type matrix: pl.DataFrame | pd.DataFrame
        :param timezone: Timezone of the timeseries data.
        :type timezone: str
        :param date_format: Format used for parsing and displaying datetime indexes.
        :type date_format: str
        """
        super().__init__(matrix, timezone=timezone)

        self._date_format: str = date_format
        self._sort_indexes()

    def __repr__(self):
        """Provide a string representation of the Matrix object."""
        return f"Forecasting Matrix : {self.matrix}"

    @property
    def date_format(self) -> str:
        """Returns the matrix date format."""
        return self._date_format

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        filters: tuple[str, str] | None = None,
        separator: str = ";",
        date_format: str = "YYYY-MM-DD HH:mm:ss",
    ) -> ForecastingMatrix:
        """
        Load a ForecastingMatrix from a file.

        :param file_path: Path to the file (CSV or Parquet).
        :type file_path: str | Path
        :return: A ForecastingMatrix object.
        :rtype: ForecastingMatrix
        """

        return cls(read_data_file(file_path, filters, separator), timezone, date_format)

    def _sort_indexes(self) -> None:
        """
        Sort the forecast matrix columns based on their datetime indexes.

        Columns are expected to be named using a specific datetime format.
        This method parses, sorts, and reorders the matrix accordingly.


        """
        if self.matrix.height == 0:
            return
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
        index: str | datetime | pendulum.DateTime,
    ) -> None:
        """
        Add a Timeseries to the matrix and keep indexes sorted.

        :param timeseries: Timeseries data to add.
        :type timeseries: Timeseries | pl.DataFrame | pd.DataFrame | dict[str, list]
        :param index: Datetime key for the new forecast.
        :type index: str | datetime
        """
        dt: str = build_datetime(index, self.date_format).format(self.date_format)

        super().add(timeseries, dt)
        self._sort_indexes()

    def __getitem__(
        self,
        index: str | datetime | pendulum.DateTime,
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
        dt: str = build_datetime(index, self.date_format).format(self.date_format)

        return super().__getitem__(dt)

    def select(self, index: str | datetime) -> Timeseries:
        """
        Get a timeseries by index.

        :param index: Index key.
        :type index: Index
        :raises KeyError: If the index is not found.
        :return: The Timeseries object.
        :rtype: Timeseries
        """
        return self.__getitem__(index)

    def delete(self, index: str | datetime | pendulum.DateTime) -> None:
        """
        Delete a timeseries by index.

        :param index: Forecast generation datetime (as string or datetime object).
        :type index: str | datetime
        :raises KeyError: If the index does not exist in the matrix.
        """
        dt: str = build_datetime(index, self.date_format).format(self.date_format)

        super().delete(dt)

        self._sort_indexes()

    def get_forecast(
        self,
        execution_date: datetime | str | pendulum.DateTime,
        start_date: datetime | str | pendulum.DateTime,
        end_date: datetime | str | pendulum.DateTime,
        timestep: str | pendulum.Duration | None = None,
    ) -> Timeseries:
        """
        Returns the most up-to-date forecast available per time row in the given window.
        Newer forecasts are prioritized. Gaps are filled from older forecasts.
        """

        execution_date = build_datetime(execution_date, self.date_format)
        start_date = build_datetime(start_date, self.date_format)
        end_date = build_datetime(end_date, self.date_format)

        if start_date > end_date:
            raise ValueError("Start date must be before end date")

        forecast_cols = (
            pl.DataFrame({"indexes": self.indexes})
            .with_columns(
                pl.col("indexes").str.strptime(
                    pl.Datetime(time_unit="us", time_zone=self.timezone),
                    pendulum_to_datetime(self.date_format),
                    strict=False,
                )
            )
            .filter(pl.col("indexes") <= execution_date)
            .with_columns(pl.col("indexes").dt.strftime(pendulum_to_datetime(self.date_format)))
            .sort("indexes", descending=True)
            .to_series()
            .to_list()
        )

        if not forecast_cols:
            raise ValueError("No forecasting dates available before execution date")

        df = self.matrix.select("time", *forecast_cols)
        forecast_expr = pl.coalesce([pl.col(col) for col in forecast_cols])

        if timestep:
            frequency_target = get_duration(timestep)
        else:
            frequency_target = get_lowest_frequency(df)

        if end_date > df["time"].max():  # type: ignore[operator]
            dt = cast("pendulum.DateTime", df["time"].max())
            column_wth_last_timestamp = df.filter(pl.col("time").eq(dt)).select(pl.selectors.numeric()).columns[0]
            frequency_columns_last_timestamp = infer_frequency(
                df.select("time", column_wth_last_timestamp).drop_nulls()
            )
            if frequency_target < frequency_columns_last_timestamp:
                datetimes_to_add = generate_datetimes(
                    start=dt,
                    end=dt + frequency_columns_last_timestamp - frequency_target,
                    freq=frequency_target,
                    timezone=self.timezone,
                )
                if len(datetimes_to_add) > 1:
                    new_df = pl.DataFrame(
                        {
                            "time": datetimes_to_add[1:],
                            column_wth_last_timestamp: [None] * len(datetimes_to_add[1:]),
                        },
                        schema={
                            "time": pl.Datetime("us", self.timezone),
                            column_wth_last_timestamp: pl.Float64(),
                        },
                    )

                    df = pl.concat([df, new_df], how="diagonal")

        limits = [infer_frequency(df.select("time", col).drop_nulls()) / frequency_target for col in forecast_cols]
        interpolate_expr = [
            pl.col(col).forward_fill(limit=int(limit))
            for (col, limit) in zip(forecast_cols, limits, strict=False)
            if limit > 1
        ]
        df = (
            df.upsample("time", every=frequency_target)
            .with_columns(interpolate_expr)
            .filter(pl.col("time").is_between(start_date, end_date))
            .select(
                [
                    pl.col("time"),
                    forecast_expr.alias("forecast"),
                ]
            )
        )

        return Timeseries(df, timezone=self.timezone)

    def set_date_format(self, date_format: str) -> None:
        new_indexes = (
            pl.DataFrame({"indexes": self.indexes})
            .with_columns(
                pl.col("indexes").str.strptime(
                    pl.Datetime(time_unit="us", time_zone=self.timezone),
                    pendulum_to_datetime(self.date_format),
                    strict=False,
                )
            )
            .sort("indexes")
            .with_columns(pl.col("indexes").dt.strftime(pendulum_to_datetime(date_format)))
            .to_series()
            .to_list()
        )

        renaming_mapping = dict(zip(self.indexes, new_indexes, strict=False))
        self.matrix = self.matrix.rename(renaming_mapping)
        self.indexes = self._get_indexes()
        self._date_format = date_format


class LazyForecastingMatrix(LazyMatrix):
    """Stores Timeseries objects lazily by scenario name, with access and deletion by name."""

    def __init__(
        self,
        matrix: LazyMatrix | pl.LazyFrame | Matrix,
        timezone: str = "UTC",
        date_format: str = "YYYY-MM-DD HH:mm:ss",
    ) -> None:
        super().__init__(matrix, timezone)
        self.date_format: str = date_format

    def __repr__(self):
        """String representation of the matrix"""
        return f"LazyForecastingMatrix with schema : {self.matrix.collect_schema()}"

    def collect(self) -> ForecastingMatrix:
        """Collect the lazy frame and return a regular ForecastingMatrix object."""
        return ForecastingMatrix(self.matrix.collect(), timezone=self.timezone, date_format=self.date_format)

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        filters: tuple[str, str] | None = None,
        separator: str = ";",
        date_format: str = "YYYY-MM-DD HH:mm:ss",
    ) -> LazyForecastingMatrix:
        """
        Load a LazyForecastingMatrix from a file.

        :param file_path: Path to the file
        :type file_path: str | Path
        :param timezone: Timezone to apply
        :type timezone: str
        :return: LazyForecastingMatrix instance
        :rtype: LazyForecastingMatrix
        """
        return cls(
            super().from_file(
                file_path,
                timezone=timezone,
                filters=filters,
                separator=separator,
            ),
            timezone,
            date_format,
        )

    def get_forecast(
        self,
        execution_date: datetime | str | pendulum.DateTime,
        start_date: datetime | str | pendulum.DateTime,
        end_date: datetime | str | pendulum.DateTime,
        timestep: str | pendulum.Duration | None = None,
    ):
        """
        Returns the most up-to-date forecast available per time row in the given window.
        Newer forecasts are prioritized. Gaps are filled from older forecasts.
        """
        return self.collect().get_forecast(
            execution_date=execution_date, start_date=start_date, end_date=end_date, timestep=timestep
        )
