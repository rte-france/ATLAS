"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

This module provides LazyTimeseries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import polars as pl
import pytz

from atlas.io.utils import scan_data_file
from atlas.math.timeseries import Timeseries


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
        interpolation_method: Literal["linear", "constant"] = "constant",
    ) -> None:
        """
        :param timeseries: The input time series data
        :type timeseries: pl.LazyFrame or LazyTimeseries or Timeseries
        :param timezone: Timezone string used to convert datetime values, defaults to "UTC"
        :type timezone: str, optional
        """
        self._check_timezone(timezone)
        self._check_interpolation_method(interpolation_method)

        self.timezone: str = timezone
        self.interpolation_method = interpolation_method

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

    @staticmethod
    def _check_interpolation_method(interpolation_method: str) -> None:
        """Check interpolation method"""
        if interpolation_method not in ("linear", "constant"):
            raise NotImplementedError("Interpolation method has to be linear, or constant")

    @staticmethod
    def _check_timezone(timezone: str) -> None:
        """
        Check if the timezone is valid.

        :raises ValueError: If the timezone is not valid
        """
        if timezone not in pytz.all_timezones:
            raise ValueError(f"Invalid timezone: {timezone}")

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        interpolation_method: Literal["linear", "constant"] = "constant",
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

        return cls(scan_data_file(file_path, filters, separator), timezone, interpolation_method)

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
            interpolation_method=self.interpolation_method,
        )
