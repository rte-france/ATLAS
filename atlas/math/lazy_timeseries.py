"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

This module provides LazyTimeseries.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pendulum
import polars as pl

from atlas.io_utils.utils import scan_data_file
from atlas.math.timeseries import Timeseries
from atlas.timing import check_timezone


class LazyTimeseries:
    """
    A lazy-evaluated time series class using a Polars LazyFrame backend.

    LazyTimeseries enables efficient, deferred computation on large time series datasets by leveraging
    Polars' lazy execution model. This is particularly useful for workflows where data is too large to fit
    in memory or when chaining multiple transformations before materializing results.
    """

    def __init__(
        self,
        timeseries: pl.LazyFrame | LazyTimeseries | Timeseries | None = None,
        timezone: str = "UTC",
    ) -> None:
        """
        :param timeseries: The input time series data
        :type timeseries: pl.LazyFrame or LazyTimeseries or Timeseries
        :param timezone: Timezone string used to convert datetime values, defaults to "UTC"
        :type timezone: str, optional
        """
        check_timezone(timezone)
        self.timezone: str = timezone

        if timeseries is None:
            self.timeseries: pl.LazyFrame = pl.LazyFrame(
                schema={
                    "time": pl.Datetime("us", time_zone=self.timezone),
                    "value": pl.Float64(),
                }
            )
        elif isinstance(timeseries, LazyTimeseries):
            self.timeseries = timeseries.to_frame()
            self.timezone = timeseries.timezone
        elif isinstance(timeseries, Timeseries):
            self.timeseries = timeseries.to_lazy()
            self.timezone = timeseries.timezone
        elif isinstance(timeseries, pl.LazyFrame):
            schema = timeseries.collect_schema().to_frame()
            time_column = schema.select(pl.selectors.datetime() | pl.selectors.date()).columns
            value_column = schema.select(pl.selectors.numeric()).columns

            if len(value_column) != 1:
                raise ValueError("Timeseries must have exactly one numeric column")
            if len(time_column) != 1:
                raise ValueError("Timeseries must have exactly one datetime column")

            self.timeseries = (
                timeseries.rename({time_column[0]: "time", value_column[0]: "value"})
                .with_columns(pl.col("time").cast(pl.Datetime("us", time_zone=timezone)))
                .sort("time")
            )

        else:
            raise ValueError("LazyTimeseries requires a LazyFrame or another Timeseries object")

    def __repr__(self):
        """String representation of the Matrix"""
        return f"LazyTimeseries with schema : {self.timeseries.collect_schema()}"

    @property
    def lazyframe(self) -> pl.LazyFrame:
        """
        Return the internal Polars LazyFrame.

        :return: The internal lazy time series data
        :rtype: pl.LazyFrame
        """
        return self.timeseries

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        filters: tuple[str, str] | None = None,
        separator: str = ";",
    ) -> LazyTimeseries:
        """
        Load a LazyTimeseries object from a file.

        :param file_path: Path to the file
        :type file_path: str or Path
        :return: Loaded LazyTimeseries object
        :rtype: LazyTimeseries
        """

        return cls(scan_data_file(file_path, filters, separator), timezone)

    def to_frame(
        self,
    ) -> pl.LazyFrame:
        """
        Return the internal Polars LazyFrame.

        :return: The internal lazy time series data
        :rtype: pl.LazyFrame or pd.DataFrame
        """
        return self.timeseries

    def collect(self) -> Timeseries:
        """
        Collect the lazy dataframe and return as a regular Timeseries.

        :return: A regular Timeseries object with the collected data
        :rtype: Timeseries
        """
        return Timeseries(
            self.timeseries.collect(),
            timezone=self.timezone,
        )

    def get_value(
        self,
        datetime: str | datetime | pendulum.DateTime,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
    ) -> float | None:
        """Return values at the given datetime. If exact match is not found, interpolate.

        :param datetime: Datetime to get value for
        :type datetime: str or datetime
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :return: The value at the timestamp requested
        :rtype: flaot
        """

        return self.collect().get_value(datetime=datetime, date_format=date_format)

    def filter(
        self,
        item: list[datetime | pendulum.DateTime | str] | datetime | pendulum.DateTime | str,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> LazyTimeseries:
        """
        Filter the LazyTimeseries based on a list of datetime.

        :param item: Datetime to filter the LazyTimeseries
        :type item: list[datetime] or datetime or pendulum.DateTime or str
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises NotImplementedError: If the times to filter type is unsupported
        :return: Filtered LazyTimeseries
        :rtype: LazyTimeseries
        """
        if isinstance(item, list):
            item = [
                pendulum.instance(i).in_tz(self.timezone)
                if isinstance(i, datetime)
                else pendulum.from_format(i, fmt=date_format).in_tz(self.timezone)
                if isinstance(i, str)
                else i.in_tz(self.timezone)
                if isinstance(i, pendulum.DateTime)
                else (_ for _ in ()).throw(NotImplementedError(f"Unsupported item in list: {type(i)}"))
                for i in item
            ]
            df = self.timeseries.filter(pl.col("time").is_in(item))
        elif isinstance(item, str):
            date = pendulum.from_format(item, fmt=date_format).in_tz(self.timezone)
            df = self.timeseries.filter(pl.col("time") == date)
        elif isinstance(item, datetime):
            date = pendulum.instance(item).in_tz(self.timezone)
            df = self.timeseries.filter(pl.col("time") == date)
        elif isinstance(item, pendulum.DateTime):
            df = self.timeseries.filter(pl.col("time") == item)
        else:
            raise NotImplementedError("Invalid filter formatting")

        if inplace:
            self.timeseries = df
            return self
        else:
            return LazyTimeseries(df, timezone=self.timezone)

    def max(self) -> float:
        """Return the max value column.

        :return: The Timeseries max value
        :rtype: float or None
        """
        return self.collect().max()

    def min(self) -> float:
        """Return the min value column.

        :return: The Timeseries min value
        :rtype: float
        """
        return self.collect().min()
