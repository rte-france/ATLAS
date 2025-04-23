"""
Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

This module provides a Timeseries class for handling time series data using Polars.
"""

from __future__ import annotations

import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pendulum
import polars as pl
import pytz

if TYPE_CHECKING:
    import pandas as pd


class Timeseries:
    """
    A time series wrapper class using Polars backend.

    :param timeseries: The input time series data.
    :type timeseries: pl.DataFrame or Timeseries
    :param timezone: Timezone string used to convert datetime values, defaults to "UTC"
    :type timezone: str, optional
    :raises ValueError: If the timeseries cannot be parsed or validated as a proper Polars DataFrame
    """

    def __init__(
        self,
        timeseries: pl.DataFrame | Timeseries | pd.DataFrame | dict[str, list],
        timezone: str = "UTC",
    ) -> None:
        self._check_timezone(timezone)

        self.timezone: str = timezone
        self.timeseries: pl.DataFrame = pl.DataFrame()

        if isinstance(timeseries, Timeseries):
            self.timeseries = timeseries.get_data()
            self.timezone = timeseries.timezone
        else:
            try:
                df = timeseries if isinstance(timeseries, pl.DataFrame) else pl.DataFrame(timeseries)
            except Exception as e:
                raise ValueError("Timeseries cannot be formatted as a DataFrame") from e

            time_column = df.select(pl.selectors.datetime() | pl.selectors.date()).columns
            if len(time_column) != 1:
                raise ValueError("Timeseries must have exactly one datetime column")
            df = df.rename({time_column[0]: "time"}).with_columns(
                pl.col("time").dt.replace_time_zone(self.timezone),
            )

            self.timeseries = df

    def __eq__(self, other: object) -> bool:
        """
        Check equality between the internal time series and another Polars DataFrame.

        :param other: The Polars DataFrame to compare with
        :type other: pl.DataFrame
        :return: True if the DataFrames are equal, False otherwise
        :rtype: bool
        """
        if isinstance(other, Timeseries):
            other = other.get_data()
            return self.timeseries.equals(other)
        raise NotImplementedError("Comparison with non-Timeseries objects is not supported")

    def __len__(self) -> int:
        """Return the number of rows in the time series."""
        return self.timeseries.height

    def __mul__(self, factor: float) -> Timeseries:
        """Multiply all numeric columns by a scalar."""
        df = self.timeseries.with_columns(pl.selectors.numeric().mul(factor))

        return Timeseries(df, self.timezone)

    def remove_na(self, inplace: bool = True) -> Timeseries:
        """
        Remove rows containing null values.

        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: The cleaned time series
        :rtype: Timeseries
        """
        df = self.timeseries.drop_nulls()
        if inplace:
            self.timeseries = df
            return self
        return Timeseries(df, self.timezone)

    def get_data(self) -> pl.DataFrame:
        """
        Return the internal Polars DataFrame.

        :return: The internal time series data
        :rtype: pl.DataFrame
        """
        return self.timeseries

    def _check_timezone(self, timezone: str) -> None:
        """
        Check if the timezone is valid.

        :raises ValueError: If the timezone is not valid
        """
        if timezone not in pytz.all_timezones:
            raise ValueError(f"Invalid timezone: {timezone}")

    def set_tz(self, timezone: str) -> None:
        """
        Convert the datetime column to a new timezone.

        :param timezone: Timezone string
        :type timezone: str
        """
        self._check_timezone(timezone)

        self.timezone = timezone
        self.timeseries = self.timeseries.with_columns(
            pl.col("time").dt.convert_time_zone(timezone),
        )

    def sort(
        self,
        variables: str | list[str],
        inplace: bool = True,
        descending: bool | list[bool] = False,
    ) -> Timeseries:
        """
        Sort the time series by the given variable(s).

        :param variables: Variable(s) to sort by
        :type variables: str or list[str]
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :param descending: Sort in descending order, defaults to False
        :type descending: bool or list[bool], optional
        :return: Sorted time series
        :rtype: Timeseries
        """
        df = self.timeseries.sort(variables, descending=descending)
        if inplace:
            self.timeseries = df
            return self
        return Timeseries(df, self.timezone)

    def upsample(
        self,
        every: str,
        inplace: bool = True,
        strategy: Literal["linear", "constant"] = "linear",
    ) -> Timeseries:
        """
        Upsample the time series to a higher frequency.

        Fills in missing timestamps by interpolating or forward-filling values.

        :param every: Frequency string (e.g., "15m", "1h") defining the new time resolution
        :type every: str
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :param strategy: Method to fill missing values: "linear" for interpolation, "constant" for forward fill
        :type strategy: str, optional
        :raises NotImplementedError: If the provided strategy is not supported
        :return: Upsampled time series
        :rtype: Timeseries
        """
        if strategy == "linear":
            df = self.timeseries.upsample(time_column="time", every=every).interpolate().fill_null(strategy="forward")
        elif strategy == "constant":
            df = self.timeseries.upsample(time_column="time", every="15m").fill_null(
                strategy="forward",
            )
        else:
            raise NotImplementedError("Unsupported interpolation strategy")

        if inplace:
            self.timeseries = df
            return self
        return Timeseries(df, self.timezone)

    def groupby(
        self,
        granularity: str | timedelta,
        agg: Literal["mean", "sum", "min", "max"] = "mean",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Group the time series dynamically by time intervals.

        :param granularity: Grouping interval (e.g., "1h", "1d")
        :type granularity: str or timedelta
        :param agg: Aggregation method, defaults to "mean"
        :type agg: Literal["mean", "sum", "min", "max"], optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises ValueError: If the aggregation function is unsupported
        :return: Grouped time series
        :rtype: Timeseries
        """
        grouped_df = self.timeseries.group_by_dynamic("time", every=granularity)
        if agg == "mean":
            df = grouped_df.agg(
                pl.selectors.numeric().mean(),
            )
        elif agg == "sum":
            df = grouped_df.agg(
                pl.selectors.numeric().sum(),
            )
        elif agg == "min":
            df = grouped_df.agg(
                pl.selectors.numeric().min(),
            )
        elif agg == "max":
            df = grouped_df.agg(
                pl.selectors.numeric().max(),
            )
        else:
            raise NotImplementedError("Unsupported aggregation function")

        if inplace:
            self.timeseries = df
            return self
        return Timeseries(df, self.timezone)

    def select(self, variables: list[str], inplace: bool = True) -> Timeseries:
        """
        Select the specified variables from the time series.

        :param variables: List of variables to exclude
        :type variables: list[str]
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Modified time series
        :rtype: Timeseries
        """
        df = self.timeseries.select(variables)
        if inplace:
            self.timeseries = df
            return self
        return Timeseries(df, self.timezone)

    def remove_duplicated(
        self,
        variables: str | list[str],
        inplace: bool = True,
    ) -> Timeseries:
        """
        Remove duplicated rows based on given variable(s).

        :param variables: Column(s) to check for duplicates
        :type variables: str or list[str]
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Deduplicated time series
        :rtype: Timeseries
        """
        df = self.timeseries.unique(subset=variables, maintain_order=True)
        if inplace:
            self.timeseries = df
            return self
        return Timeseries(df, self.timezone)

    def join(
        self,
        other: Timeseries | pl.DataFrame,
        by: str = "time",
        how: Literal["inner", "left", "right", "full", "semi", "anti", "cross", "outer"] = "inner",
        suffixes: str = "_right",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Merge this time series with another.

        :param other: Another Timeseries object or Polars DataFrame to merge
        :type other: Timeseries or pl.DataFrame
        :param by: Column name to join on, defaults to "time"
        :type by: str, optional
        :param how: Type of join operation, defaults to "inner"
        :type how: Literal["inner", "left", "right", "full", "semi", "anti", "cross", "outer"], optional
        :param suffixes: Suffix to use for overlapping column names, defaults to None
        :type suffixes: str or None, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Merged time series
        :rtype: Timeseries
        """
        if isinstance(other, Timeseries):
            other = other.timeseries
        df = self.timeseries.join(other, on=by, how=how, suffix=suffixes)
        if inplace:
            self.timeseries = df
            return self
        return Timeseries(df, self.timezone)

    def drop(self, variables: list[str], inplace: bool = True) -> Timeseries:
        """
        Remove specified variables from the time series.

        :param variables: Column names to remove
        :type variables: list[str]
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Modified time series
        :rtype: Timeseries
        """
        df = self.timeseries.drop(variables)
        if inplace:
            self.timeseries = df
            return self
        return Timeseries(df, self.timezone)

    def get_granularity(self, unit: Literal["hour", "minute", "second"] = "hour") -> float:
        """
        Compute the time interval (granularity) between data points.

        :param unit: Time unit to return the granularity in, defaults to "hour"
        :type unit: Literal["hour", "minute", "second"], optional
        :raises ValueError: If fewer than two time points exist or if unit is unsupported
        :return: Time interval in the specified unit
        :rtype: float
        """
        times = self.timeseries["time"].to_list()
        if len(times) < 2:  # noqa: PLR2004
            raise ValueError("Not enough time points to calculate granularity")
        delta: float = (times[1] - times[0]).total_seconds()

        if unit == "hour":
            return delta / 3600
        if unit == "minute":
            return delta / 60
        if unit == "second":
            return delta
        raise ValueError("Unsupported unit")

    def rename(self, old_cols: list[str], new_cols: list[str], inplace: bool = True) -> Timeseries:
        """
        Rename columns in the time series.

        :param old_cols: List of current column names
        :type old_cols: list[str]
        :param new_cols: List of new column names
        :type new_cols: list[str]
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Modified time series or None
        :rtype: Timeseries or None
        """
        df = self.timeseries.rename(dict(zip(old_cols, new_cols, strict=False)))
        if inplace:
            self.timeseries = df
            return self
        return Timeseries(df, self.timezone)

    def export(
        self,
        path: str | Path,
        file_format: Literal["csv", "parquet", "pickle"] = "csv",
    ) -> None:
        """
        Export the time series to a file.

        :param path: Destination file path
        :type path: str
        :param file_format: Export file format, defaults to "csv"
        :type file_format: Literal["csv", "parquet", "pickle"], optional
        :raises ValueError: If file extension doesn't match format
        :raises NotImplementedError: If the file format is not supported
        """
        file_format_lower = file_format.lower()

        if isinstance(path, Path):
            path = str(path)
        if not path.lower().endswith(file_format_lower):
            raise ValueError("Format and file extension don't match.")

        if file_format_lower == "csv":
            self.timeseries.write_csv(path)
        elif file_format_lower == "parquet":
            self.timeseries.write_parquet(path)
        elif file_format_lower == "pickle":
            with open(path, "wb") as f:
                pickle.dump(self, f)
        else:
            raise NotImplementedError("Format not supported")

    def filter(
        self,
        item: list[datetime] | datetime | pendulum.DateTime | str,
        inplace: bool = True,
    ) -> Timeseries:
        """
        Filter the time series based on a condition.

        :param condition: Condition to filter by
        :type condition: str or pl.Expr
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Filtered time series
        :rtype: Timeseries
        """
        if isinstance(item, list):
            df = self.timeseries.filter(pl.col("time").is_in(item))
        elif isinstance(item, str):
            date = pendulum.parse(item, tz=self.timezone)
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
        return Timeseries(df, self.timezone)

    # def __getitem__(
    #     self,
    #     item: list[datetime] | datetime | str | pendulum.DateTime,
    # ) -> Timeseries:
    #     """Get a subset of the time series.

    #     :param item: Column name, index, or slice to select
    #     :type item: int, slice, list[str], list[int], or list[slice]
    #     :return: Subset of the time series
    #     :rtype: Timeseries
    #     """
    #     return self.filter(item, inplace=False).get_data()
