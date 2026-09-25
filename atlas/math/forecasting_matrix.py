"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ForecastingMatrix
"""

from __future__ import annotations

import copy
from bisect import bisect_left, bisect_right
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Self, cast

import pendulum
import polars as pl
from pydantic_core import core_schema

from atlas.io_utils.utils import read_data_file
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.lazy_matrix import LazyScenarioMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.timing import (
    build_datetime,
    epoch_key,
    generate_datetimes,
    get_duration,
    get_lowest_frequency,
    infer_frequency,
    pendulum_to_datetime,
)
from atlas.type import TimeseriesDict

if TYPE_CHECKING:
    import pandas as pd

_FORECAST_CACHE_SIZE = 4
"""Resolved forecasts kept per matrix. Workflows move from one execution date to the next, so
only the most recent resolutions are worth keeping."""

_ForecastKey = tuple[str, pendulum.Duration | None]
"""Most recent available forecast column, and the requested timestep (None: lowest frequency)."""


def _infer_column_frequency(df: pl.DataFrame, col: str) -> pendulum.Duration:
    """Infer the step of one forecast column, ignoring its nulls. Defaults to 1 hour."""
    col_df = df.select("time", col).drop_nulls()
    if col_df.height > 1:
        return infer_frequency(col_df)
    return pendulum.duration(hours=1)


@dataclass(frozen=True)
class _ResolvedForecast:
    """
    Most recent forecast per row, resolved over the whole span of a matrix.

    :param frame: ``time`` and ``forecast`` columns on the ``frequency`` grid.
    :param epochs: Instants of ``frame["time"]`` in epoch microseconds, to slice windows by bisection.
    :param frequency: Step of the grid.
    """

    frame: pl.DataFrame
    epochs: list[int]
    frequency: pendulum.Duration

    def window(
        self,
        start_date: pendulum.DateTime,
        end_date: pendulum.DateTime,
        default_value: float | None,
        timezone: str,
    ) -> Timeseries:
        """
        Return the rows between ``start_date`` and ``end_date`` (both included).

        :param default_value: If set, every step of the window is returned, using this value
            where no forecast is found.
        """
        lower = bisect_left(self.epochs, epoch_key(start_date))
        upper = bisect_right(self.epochs, epoch_key(end_date))
        df = self.frame.slice(lower, upper - lower)

        if default_value is not None:
            # we must set a value for each index between start and end date
            # using default value if none is found
            full_index = pl.DataFrame(
                {"time": generate_datetimes(start=start_date, end=end_date, freq=self.frequency, timezone=timezone)}
            )
            df = full_index.join(df, on="time", how="left").with_columns(pl.col("forecast").fill_null(default_value))

        return Timeseries(df, timezone=timezone)


def _resolve_forecast(
    df: pl.DataFrame,
    forecast_cols: list[str],
    timestep: pendulum.Duration | None,
    timezone: str,
    column_frequency: Callable[[pl.DataFrame, str], pendulum.Duration],
) -> _ResolvedForecast:
    """
    Resolve the most recent forecast per row over the whole span of ``df``.

    Newer forecasts are prioritized and gaps are filled from older ones. A window is only
    filtered after the forward fill and the row-wise coalesce, so slicing this result gives the
    same rows as resolving the window directly. The padding after the last timestamp, which
    only matters to windows ending after the data, is always added.

    :param df: ``time`` column and the available forecast columns.
    :param forecast_cols: Available forecast columns, most recent first.
    :param timestep: Target step. If None, the lowest frequency found in ``df`` is used.
    :param timezone: Timezone of the matrix.
    :param column_frequency: Returns the step of a forecast column of ``df``.
    """
    frequency_target = timestep if timestep is not None else get_lowest_frequency(df)

    limits = {col: column_frequency(df, col) / frequency_target for col in forecast_cols}

    max_time = df["time"].max()
    if max_time is not None:
        dt = cast("pendulum.DateTime", max_time)
        last_row = df.filter(pl.col("time").eq(dt))
        column_wth_last_timestamp = None
        for col in forecast_cols:
            if last_row[col][0] is not None:
                column_wth_last_timestamp = col
                break

        if column_wth_last_timestamp:
            frequency_columns_last_timestamp = column_frequency(df, column_wth_last_timestamp)
            if frequency_target < frequency_columns_last_timestamp:
                datetimes_to_add = generate_datetimes(
                    start=dt,
                    end=dt + frequency_columns_last_timestamp - frequency_target,
                    freq=frequency_target,
                    timezone=timezone,
                )
                if len(datetimes_to_add) > 1:
                    new_df = pl.DataFrame(
                        {
                            "time": datetimes_to_add[1:],
                            column_wth_last_timestamp: [None] * len(datetimes_to_add[1:]),
                        },
                        schema={
                            "time": pl.Datetime("us", timezone),
                            column_wth_last_timestamp: pl.Float64(),
                        },
                    )
                    df = pl.concat([df, new_df], how="diagonal")

    interpolate_expr = [pl.col(col).forward_fill(limit=int(limits[col])) for col in forecast_cols if limits[col] > 1]
    forecast_expr = pl.coalesce([pl.col(col) for col in forecast_cols])

    frame = (
        df.upsample("time", every=frequency_target)
        .with_columns(interpolate_expr)
        .select(pl.col("time"), forecast_expr.alias("forecast"))
    )
    return _ResolvedForecast(frame, frame["time"].dt.epoch("us").to_list(), frequency_target)


class _ForecastCache:
    """
    Data derived from the frame of a forecasting matrix: parsed indexes, column frequencies and
    the most recently resolved forecasts.

    Everything is dropped as soon as the frame is replaced, which every mutation of the matrix
    does (``add``, ``delete``, ``set_frequency``, ``abs``, ``set_date_format``, ...), so callers
    must call :meth:`sync` with the current frame before reading.
    """

    def __init__(self) -> None:
        self._frame: pl.DataFrame | pl.LazyFrame | None = None
        self._indexes: tuple[list[datetime], list[str]] | None = None
        self._frequencies: dict[str, pendulum.Duration] = {}
        self._resolved: OrderedDict[_ForecastKey, _ResolvedForecast] = OrderedDict()

    def sync(self, frame: pl.DataFrame | pl.LazyFrame) -> None:
        """Drop everything if ``frame`` is not the frame the cache was built from."""
        if frame is not self._frame:
            self._frame = frame
            self._indexes = None
            self._frequencies = {}
            self._resolved.clear()

    def available_forecasts(
        self,
        indexes: list[str],
        execution_date: pendulum.DateTime,
        timezone: str,
        date_format: str,
    ) -> list[str]:
        """Return the forecast columns issued on or before ``execution_date``, most recent first."""
        if self._indexes is None:
            parsed = (
                pl.DataFrame({"indexes_str": indexes}, schema={"indexes_str": pl.String})
                .with_columns(
                    pl.col("indexes_str")
                    .str.strptime(
                        pl.Datetime(time_unit="us", time_zone=timezone),
                        pendulum_to_datetime(date_format),
                        strict=False,
                    )
                    .alias("indexes_dt")
                )
                .drop_nulls("indexes_dt")
                .sort("indexes_dt")
            )
            self._indexes = (parsed["indexes_dt"].to_list(), parsed["indexes_str"].to_list())

        issued, names = self._indexes
        return names[: bisect_right(issued, execution_date)][::-1]

    def column_frequency(self, df: pl.DataFrame, col: str) -> pendulum.Duration:
        """Return the step of a forecast column, inferred once."""
        if col not in self._frequencies:
            self._frequencies[col] = _infer_column_frequency(df, col)
        return self._frequencies[col]

    def resolved(self, key: _ForecastKey, resolve: Callable[[], _ResolvedForecast]) -> _ResolvedForecast:
        """Return the forecast resolved for ``key``, calling ``resolve`` on a miss."""
        resolved = self._resolved.get(key)
        if resolved is None:
            resolved = resolve()
            self._resolved[key] = resolved
            if len(self._resolved) > _FORECAST_CACHE_SIZE:
                self._resolved.popitem(last=False)
        else:
            self._resolved.move_to_end(key)
        return resolved


class ForecastingMatrix(ScenarioMatrix):
    """
    A matrix structure for managing collections of forecast time series, indexed by forecast generation time.

    The ForecastingMatrix is designed to store and organize multiple time series forecasts,
    where each column (except for the "time" column) represents a forecast generated at a specific datetime.
    """

    def __init__(
        self,
        matrix: pl.DataFrame | pd.DataFrame | ScenarioMatrix | None = None,
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
        self._forecast_cache = _ForecastCache()

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.is_instance_schema(
            cls,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: "forecasting_matrix", when_used="json"
            ),
        )

    def __repr__(self):
        """Provide a string representation of the ScenarioMatrix object."""
        return f"Forecasting ScenarioMatrix : {self.matrix}"

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
        drop_null_columns: bool = False,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
    ) -> ForecastingMatrix:
        """
        Load a ForecastingMatrix from a file.

        :param file_path: Path to the file (CSV or Parquet).
        :type file_path: str | Path
        :param drop_null_columns: If True, drop forecast columns that are entirely null once
            ``filters`` is applied. Files stacking several attributes in the same table can
            leave columns that only belonged to another attribute, all-null after filtering.
        :type drop_null_columns: bool
        :return: A ForecastingMatrix object.
        :rtype: ForecastingMatrix
        """

        return cls(
            read_data_file(file_path, filters, separator, drop_null_columns=drop_null_columns), timezone, date_format
        )

    def _sort_indexes(self) -> None:
        """
        Sort the forecast matrix columns based on their datetime indexes.

        Columns are expected to be named using a specific datetime format.
        This method parses, sorts, and reorders the matrix accordingly.

        Nothing is sorted when the matrix holds no forecast, which happens transiently while
        replacing the only forecast of a matrix: an empty index list carries no datetime to parse.
        """
        if self.matrix.height == 0 or not self.indexes:
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
        timeseries: AbstractTimeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict,
        index: str | datetime | pendulum.DateTime,
        inplace: bool = True,
    ) -> Self:
        """
        Add a Timeseries to the matrix and keep indexes sorted.

        :param timeseries: Timeseries data to add.
        :type timeseries: Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict
        :param index: Datetime key for the new forecast.
        :type index: str | datetime
        :param inplace: If True (default), modify the matrix in place. If False, return a new matrix.
        :type inplace: bool
        """
        dt: str = build_datetime(index, self.date_format).format(self.date_format)
        result = super().add(timeseries, dt, inplace=inplace)
        result._sort_indexes()
        return result

    def __contains__(self, index: str | datetime | pendulum.DateTime) -> bool:
        """
        Check if an index exists in the forecasting matrix.

        :param index: Forecast generation datetime (as string or datetime object).
        :type index: str | datetime | pendulum.DateTime
        :return: True if index exists, False otherwise.
        :rtype: bool
        """
        dt: str = build_datetime(index, self.date_format).format(self.date_format)
        return dt in self.indexes

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

    def delete(self, index: str | datetime | pendulum.DateTime, inplace: bool = True) -> Self:
        """
        Delete a timeseries by index.

        :param index: Forecast generation datetime (as string or datetime object).
        :type index: str | datetime
        :param inplace: If True (default), modify the matrix in place. If False, return a new matrix.
        :type inplace: bool
        :raises KeyError: If the index does not exist in the matrix.
        """
        dt: str = build_datetime(index, self.date_format).format(self.date_format)
        result = super().delete(dt, inplace=inplace)
        result._sort_indexes()
        return result

    def replace(
        self,
        index: str | datetime | pendulum.DateTime,
        timeseries: Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict,
        inplace: bool = True,
    ) -> Self:
        """
        Replace a Timeseries in the matrix and keep indexes sorted.

        :param timeseries: Timeseries data to add.
        :type timeseries: Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict
        :param index: Datetime key for the new forecast.
        :type index: str | datetime
        :param inplace: If True (default), modify the matrix in place. If False, return a new matrix.
        :type inplace: bool
        """
        target = self if inplace else copy.deepcopy(self)
        target.delete(index=index)
        target.add(timeseries=timeseries, index=index)
        return target

    def upsert(
        self,
        index: str | datetime | pendulum.DateTime,
        timeseries: Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict,
        inplace: bool = True,
    ) -> Self:
        """
        Add a Timeseries at ``index``, replacing any forecast already stored there.

        :param index: Datetime key for the forecast.
        :type index: str | datetime | pendulum.DateTime
        :param timeseries: Timeseries data to store.
        :type timeseries: Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict
        :param inplace: If True (default), modify the matrix in place. If False, return a new matrix.
        :type inplace: bool
        :return: The updated matrix.
        :rtype: Self
        """
        if index in self:
            return self.replace(index, timeseries, inplace=inplace)
        return self.add(timeseries, index, inplace=inplace)

    def get_forecast(
        self,
        execution_date: datetime | str | pendulum.DateTime,
        start_date: datetime | str | pendulum.DateTime,
        end_date: datetime | str | pendulum.DateTime,
        timestep: str | timedelta | pendulum.Duration | None = None,
        default_value: float | None = None,
    ) -> Timeseries:
        """
        Returns the most up-to-date forecast available per time row in the given window.
        Newer forecasts are prioritized. Gaps are filled from older forecasts.

        The forecast is resolved once over the whole span of the matrix for the forecasts
        available at ``execution_date`` and the requested ``timestep``, then every window,
        including point queries (``start_date == end_date``), is sliced from it. The last
        resolutions are kept until the matrix is modified.

        :param execution_date: The reference date for determining which forecasts are available.
                              Only forecasts made on or before this date will be considered.
        :type execution_date: datetime | str | pendulum.DateTime
        :param start_date: Start date of the forecast window to retrieve.
        :type start_date: datetime | str | pendulum.DateTime
        :param end_date: End date of the forecast window to retrieve.
        :type end_date: datetime | str | pendulum.DateTime
        :param timestep: Target frequency for the output timeseries. If None, the lowest
                        frequency found in the data will be used.
        :type timestep: str | pendulum.Duration | None
        :param default_value: default value used for indexes where no value is found
        :type default_value: float | None
        :raises ValueError: If start_date is after end_date or if no forecasting dates
                           are available before the execution date.
        :return: A timeseries containing the most recent forecast values for each timestamp
                in the specified window, with gaps filled using older forecasts.
        :rtype: Timeseries
        """
        execution_date = build_datetime(execution_date, self.date_format)
        start_date = build_datetime(start_date, self.date_format)
        end_date = build_datetime(end_date, self.date_format)

        if start_date > end_date:
            raise ValueError("Start date must be before end date")

        cache = self._forecast_cache
        cache.sync(self.matrix)
        forecast_cols = cache.available_forecasts(self.indexes, execution_date, self.timezone, self.date_format)
        if not forecast_cols:
            raise ValueError("No forecasting dates available before execution date")

        target = get_duration(timestep) if timestep else None
        resolved = cache.resolved(
            (forecast_cols[0], target),
            lambda: _resolve_forecast(
                self.matrix.select("time", *forecast_cols),
                forecast_cols,
                target,
                self.timezone,
                cache.column_frequency,
            ),
        )
        return resolved.window(start_date, end_date, default_value, self.timezone)

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


class LazyForecastingMatrix(LazyScenarioMatrix):
    """Stores Timeseries objects lazily by scenario name, with access and deletion by name."""

    def __init__(
        self,
        matrix: LazyScenarioMatrix | pl.LazyFrame | ScenarioMatrix,
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
        drop_null_columns: bool = False,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
    ) -> LazyForecastingMatrix:
        """
        Load a LazyForecastingMatrix from a file.

        :param file_path: Path to the file
        :type file_path: str | Path
        :param timezone: Timezone to apply
        :type timezone: str
        :param drop_null_columns: If True, drop forecast columns that are entirely null once
            ``filters`` is applied. Files stacking several attributes in the same table can
            leave columns that only belonged to another attribute, all-null after filtering.
        :type drop_null_columns: bool
        :return: LazyForecastingMatrix instance
        :rtype: LazyForecastingMatrix
        """
        return cls(
            super().from_file(
                file_path,
                timezone=timezone,
                filters=filters,
                separator=separator,
                drop_null_columns=drop_null_columns,
            ),
            timezone,
            date_format,
        )

    def __contains__(self, index: str | datetime | pendulum.DateTime) -> bool:
        """
        Check if an index exists in the lazy forecasting matrix.

        :param index: Forecast generation datetime (as string or datetime object).
        :type index: str | datetime | pendulum.DateTime
        :return: True if index exists, False otherwise.
        :rtype: bool
        """
        dt: str = build_datetime(index, self.date_format).format(self.date_format)
        return dt in self.indexes

    def add(
        self,
        timeseries: LazyTimeseries | pl.LazyFrame | Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict,
        index: str | datetime | pendulum.DateTime,
        inplace: bool = True,
    ) -> Self:
        """
        Add a timeseries to the lazy forecasting matrix.

        :param timeseries: Timeseries data to add.
        :type timeseries: Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict
        :param index: Datetime key for the new forecast.
        :type index: str | datetime | pendulum.DateTime
        :param inplace: If True (default), modify the matrix in place. If False, return a new matrix.
        :type inplace: bool
        :raises KeyError: If index already exists in the matrix.
        """
        dt: str = build_datetime(index, self.date_format).format(self.date_format)
        return super().add(timeseries, dt, inplace=inplace)

    def delete(self, index: str | datetime | pendulum.DateTime, inplace: bool = True) -> Self:
        """
        Delete a timeseries by index.

        :param index: Forecast generation datetime (as string or datetime object).
        :type index: str | datetime | pendulum.DateTime
        :param inplace: If True (default), modify the matrix in place. If False, return a new matrix.
        :type inplace: bool
        :raises KeyError: If the index does not exist in the matrix.
        """
        dt: str = build_datetime(index, self.date_format).format(self.date_format)
        return super().delete(dt, inplace=inplace)

    def replace(
        self,
        index: str | datetime | pendulum.DateTime,
        timeseries: LazyTimeseries | pl.LazyFrame | Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict,
        inplace: bool = True,
    ) -> Self:
        """
        Replace a Timeseries in the matrix and keep indexes sorted.

        :param timeseries: Timeseries data to add.
        :type timeseries: Timeseries | pl.DataFrame | pd.DataFrame | dict[str, list]
        :param index: Datetime key for the new forecast.
        :type index: str | datetime
        :param inplace: If True (default), modify the matrix in place. If False, return a new matrix.
        :type inplace: bool
        """
        target = self if inplace else copy.deepcopy(self)
        target.delete(index=index)
        target.add(timeseries=timeseries, index=index)
        return target

    def upsert(
        self,
        index: str | datetime | pendulum.DateTime,
        timeseries: LazyTimeseries | pl.LazyFrame | Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict,
        inplace: bool = True,
    ) -> Self:
        """
        Add a Timeseries at ``index``, replacing any forecast already stored there.

        :param index: Datetime key for the forecast.
        :type index: str | datetime | pendulum.DateTime
        :param timeseries: Timeseries data to store.
        :type timeseries: LazyTimeseries | pl.LazyFrame | Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict
        :param inplace: If True (default), modify the matrix in place. If False, return a new matrix.
        :type inplace: bool
        :return: The updated matrix.
        :rtype: Self
        """
        if index in self:
            return self.replace(index, timeseries, inplace=inplace)
        return self.add(timeseries, index, inplace=inplace)

    def get_forecast(
        self,
        execution_date: datetime | str | pendulum.DateTime,
        start_date: datetime | str | pendulum.DateTime,
        end_date: datetime | str | pendulum.DateTime,
        timestep: str | pendulum.Duration | None = None,
        default_value: float | None = None,
    ) -> Timeseries:
        """
        Returns the most up-to-date forecast available per time row in the given window.
        Newer forecasts are prioritized. Gaps are filled from older forecasts.

        :param execution_date: The reference date for determining which forecasts are available.
                              Only forecasts made on or before this date will be considered.
        :type execution_date: datetime | str | pendulum.DateTime
        :param start_date: Start date of the forecast window to retrieve.
        :type start_date: datetime | str | pendulum.DateTime
        :param end_date: End date of the forecast window to retrieve.
        :type end_date: datetime | str | pendulum.DateTime
        :param timestep: Target frequency for the output timeseries. If None, the lowest
                        frequency found in the data will be used.
        :type timestep: str | pendulum.Duration | None
        :param default_value: Default value used for indexes where no value is found
        :type default_value: float | None
        :raises ValueError: If start_date is after end_date or if no forecasting dates
                           are available before the execution date.
        :return: A timeseries containing the most recent forecast values for each timestamp
                in the specified window, with gaps filled using older forecasts.
        :rtype: Timeseries
        """
        return self.collect().get_forecast(
            execution_date=execution_date,
            start_date=start_date,
            end_date=end_date,
            timestep=timestep,
            default_value=default_value,
        )

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.is_instance_schema(
            cls,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: "forecasting_matrix", when_used="json"
            ),
        )
