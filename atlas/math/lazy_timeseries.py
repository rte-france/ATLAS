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

from atlas.math.timeseries import Timeseries


class LazyTimeseries:
    """
    An unloaded time series class using Polars lazy evaluation.

    This class allows working with large datasets without loading them entirely into memory.

    :param timeseries: The input time series data
    :type timeseries: pl.LazyFrame or LazyTimeseries or Timeseries
    :param timezone: Timezone string used to convert datetime values, defaults to "UTC"
    :type timezone: str, optional
    """

    def __init__(
        self,
        timeseries: pl.LazyFrame | LazyTimeseries | Timeseries,
        timezone: str = "UTC",
        interpolation_method: Literal["linear", "constant"] = "constant",
    ) -> None:
        self._check_timezone(timezone)
        self._check_interpolation_method(interpolation_method)

        self.timezone: str = timezone
        self.interpolation_method = interpolation_method

        if timeseries is None:
            # Create an empty lazy DataFrame
            self.timeseries: pl.LazyFrame = pl.LazyFrame(
                schema={
                    "time": pl.Datetime("us", time_zone=self.timezone),
                    "value": pl.Float64(),
                }
            )
        elif isinstance(timeseries, LazyTimeseries):
            self.timeseries = timeseries.get_data()
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
    def from_file(cls, file_path: str | Path, separator: str = ";", timezone: str = "UTC") -> LazyTimeseries:
        """
        Load a LazyTimeseries object from a file.

        :param file_path: Path to the file
        :type file_path: str or Path
        :raises ValueError: If file format is not supported
        :return: Loaded LazyTimeseries object
        :rtype: LazyTimeseries
        """
        if isinstance(file_path, str):
            file_path = Path(file_path)

        if file_path.suffix == ".csv":
            return cls(pl.scan_csv(file_path, separator=separator), timezone=timezone)
        if file_path.suffix == ".parquet":
            return cls(pl.scan_parquet(file_path), timezone=timezone)
        raise ValueError("Unsupported file format. Only CSV and Parquet are supported.")

    def get_data(
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
