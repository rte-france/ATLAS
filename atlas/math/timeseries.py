"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

This module provides a Timeseries class for handling Timeseries data using Polars.
"""

from __future__ import annotations

import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd
import pendulum
import plotly
import plotly.express as px
import plotly.graph_objects
import polars as pl
import pytz

from atlas.timing import build_datetime, infer_frequency


class Timeseries:
    """
    A flexible and efficient time series class using a Polars backend.

    The Timeseries class provides a unified interface for handling, analyzing, and visualizing
    time series data. It supports a variety of input formats (Polars DataFrame, Pandas DataFrame,
    dictionary, or another Timeseries instance) and ensures robust handling of time zones and
    interpolation methods.
    """

    def __init__(
        self,
        timeseries: pl.DataFrame | Timeseries | pd.DataFrame | dict[str, list] | None = None,
        timezone: str = "UTC",
        interpolation_method: Literal["linear", "constant"] = "constant",
    ) -> None:
        """
        :param timeseries: The input Timeseries data.
        :type timeseries: pl.DataFrame or Timeseries
        :param timezone: Timezone string used to convert datetime values, defaults to "UTC"
        :type timezone: str, optional
        """
        self._check_timezone(timezone)
        self._check_interpolation_method(interpolation_method)

        self.interpolation_method: Literal["constant", "linear"] = interpolation_method
        self.timezone: str = timezone

        self._check_timeseries(timeseries)
        self._set_timeseries(timeseries, timezone)

        self.frequency: pendulum.Duration = infer_frequency(self.timeseries)

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        interpolation_method: Literal["linear", "constant"] = "constant",
        filters: tuple[str, str] | None = None,
        separator: str = ";",
    ) -> Timeseries:
        """
        Load a Timeseries object from a file.

        :param file_path: Path to the file
        :type file_path: str or Path
        :raises ValueError: If file format is not supported
        :return: Loaded Timeseries object
        :rtype: Timeseries
        """

        return cls(cls._read_data_file(file_path, filters, separator), timezone, interpolation_method)

    @staticmethod
    def _read_data_file(
        file_path: str | Path,
        filters: tuple[str, str] | None = None,
        separator: str = ";",
    ) -> pl.DataFrame:
        """Read a dataframe from csv or parquet"""
        if isinstance(file_path, str):
            file_path = Path(file_path)
        if file_path.suffix == ".csv":
            timeseries = pl.read_csv(file_path, separator=separator, try_parse_dates=True)
        elif file_path.suffix == ".parquet":
            timeseries = pl.read_parquet(file_path)
        else:
            raise ValueError("Unsupported file format. Only CSV and Parquet are supported.")
        if filters:
            timeseries = timeseries.filter(pl.col(f"{filters[0]}") == filters[1]).drop(filters[0])

        return timeseries

    @classmethod
    def describe(cls, timeseries: pd.DataFrame | pl.DataFrame | Timeseries) -> dict[str, Any]:
        """
        Get metadata about the timeseries.

        :param timeseries: DataFrame containing the timeseries data.
        :type timeseries: pd.DataFrame | pl.DataFrame | Timeseries
        :return: A dictionnary containing timeseries metadata
        :rtype: dict[str, Any]
        """
        if isinstance(timeseries, pd.DataFrame):
            df = pl.DataFrame(timeseries)
        elif isinstance(timeseries, Timeseries):
            df = timeseries.dataframe  # type: ignore[assignment]
        elif isinstance(timeseries, pl.DataFrame):
            df = timeseries
        elif isinstance(timeseries, str) | isinstance(timeseries, Path):
            file_path = Path(timeseries)  # type: ignore[arg-type]
            df = cls._read_data_file(file_path)
        else:
            raise NotImplementedError("Can't parse input data. Provide a dataframe or a Timeseries")

        summary = {
            "shape": df.shape,
            "memory_mb": f"{df.estimated_size('mb'):.02f}",
        }

        datetime_cols = df.select(pl.selectors.datetime() | pl.selectors.date()).columns
        string_cols = df.select(pl.selectors.string()).columns
        numeric_cols = df.select(pl.selectors.numeric()).columns

        if len(datetime_cols) == 1:
            dt_col = datetime_cols[0]
            dt_series = df[dt_col]
            summary["datetime"] = {  # type: ignore[assignment]
                "column": dt_col,
                "min": pendulum.instance(dt_series.min()).to_datetime_string(),  # type: ignore[attr-defined, arg-type]
                "max": pendulum.instance(dt_series.max()).to_datetime_string(),  # type: ignore[attr-defined, arg-type]
                "nulls": dt_series.null_count(),
            }
        else:
            raise ValueError("Expected one datetime column exactly")

        if len(string_cols) == 1:
            cat_col = string_cols[0]
            cat_series = df[cat_col]
            categories = sorted(cat_series.unique().to_list())
            summary["categorical"] = {  # type: ignore[assignment]
                "column": cat_col,
                "categories": categories,
                "nulls": cat_series.null_count(),
            }

        if len(numeric_cols) == 1:
            num_col = numeric_cols[0]
            num_series = df[num_col]
            summary["numerical"] = {  # type: ignore[assignment]
                "column": num_col,
                "nulls": num_series.null_count(),
                "min": num_series.min(),
                "max": num_series.max(),
            }

        return summary

    def _check_timeseries(self, timeseries: pl.DataFrame | Timeseries | pd.DataFrame | dict[str, list] | None) -> None:
        if timeseries is None or isinstance(timeseries, Timeseries):
            return
        df = timeseries if isinstance(timeseries, pl.DataFrame) else pl.DataFrame(timeseries)

        time_column = df.select(pl.selectors.datetime() | pl.selectors.date()).columns
        value_column = df.select(pl.selectors.numeric()).columns

        if len(value_column) != 1:
            raise ValueError("Timeseries must have exactly one numeric column")
        if len(time_column) != 1:
            raise ValueError("Timeseries must have exactly one datetime column")
        if len(value_column) + len(time_column) != len(df.columns):
            raise ValueError("Timeseries must have two columns, one for datetime and one numerical values")

    def _set_timeseries(
        self,
        timeseries: pl.DataFrame | Timeseries | pd.DataFrame | dict[str, list] | None,
        timezone: str,
    ) -> None:
        if timeseries is None:
            self.timeseries = pl.DataFrame(
                schema={
                    "time": pl.Datetime("us", time_zone=self.timezone),
                    "value": pl.Float64(),
                }
            )

        elif isinstance(timeseries, Timeseries):
            self.timeseries = timeseries.dataframe  # type: ignore[assignment]
        else:
            try:
                df = timeseries if isinstance(timeseries, pl.DataFrame) else pl.DataFrame(timeseries)
            except Exception as e:
                raise ValueError("Timeseries cannot be formatted as a DataFrame") from e

            time_column = df.select(pl.selectors.datetime() | pl.selectors.date()).columns
            value_column = df.select(pl.selectors.numeric()).columns

            self.timeseries = df.rename({time_column[0]: "time", value_column[0]: "value"}).with_columns(
                pl.col("time").cast(pl.Datetime("us", time_zone=timezone))
            )

            self.sort()

    def __repr__(self):
        """Provide a string representation of the Timeseries object."""
        return f"Timeseries : {self.timeseries}"

    def __eq__(self, other: object) -> bool:
        """
        Implement the equality between two Timeseries:

        :param other: The Polars DataFrame to compare with
        :type other: pl.DataFrame
        :raises NotImplementedError: If the object to compare is not a Timeseries
        :return: True if the DataFrames are equal, False otherwise
        :rtype: bool
        """
        if isinstance(other, Timeseries):
            other = other.dataframe
            return self.timeseries.equals(other)
        raise TypeError("Comparison with non-Timeseries objects is not supported")

    def __len__(self) -> int:
        """Return the number of rows in the Timeseries.

        :return: Number of rows in the Timeseries
        :rtype: bool
        """
        return self.timeseries.height

    def __mul__(self, other: float | Timeseries) -> Timeseries:
        """Multiply all numeric columns by a scalar or another Timeseries.

        :raises TypeError: If the object is not a timeseries or a float
        :return: The Timeseries where all numeric columns are multiplied by a scalar or another Timeseries
        :rtype: Timeseries
        """
        if isinstance(other, int | float):
            df = self.timeseries.with_columns(pl.selectors.numeric().mul(other))
        elif isinstance(other, Timeseries):
            if self.frequency < other.frequency:
                other.upsample(self.frequency)
            elif self.frequency > other.frequency:
                self.upsample(other.frequency)

            df = (
                self._join(
                    other=other,
                    how="full",
                )
                .fill_null(1)
                .with_columns(pl.col("value").mul(pl.col("value_right")).alias("value"))
                .select("time", "value")
            )
        else:
            raise TypeError("Timeseries can't be multiplied")

        return Timeseries(df, self.timezone)

    def __add__(self, other: float | Timeseries) -> Timeseries:
        """Add all numeric columns by a scalar or timeseries.

        :raises TypeError: If the object is not a timeseries or a float
        :return: The Timeseries where a scalar or another Timeseries are added to all numeric columns
        :rtype: Timeseries
        """
        if isinstance(other, int | float):
            df = self.timeseries.with_columns(pl.selectors.numeric().add(other))
        elif isinstance(other, Timeseries):
            if self.frequency < other.frequency:
                other.upsample(self.frequency)
            elif self.frequency > other.frequency:
                self.upsample(other.frequency)

            df = (
                self._join(
                    other=other,
                    how="full",
                )
                .fill_null(0)
                .with_columns(pl.col("value").add(pl.col("value_right")).alias("value"))
                .select("time", "value")
            )
        else:
            raise TypeError("Timeseries can't perform addition")

        return Timeseries(df, self.timezone)

    def __sub__(self, other: float | Timeseries) -> Timeseries:
        """Subtract all numeric columns by a scalar or timeseries.

        :raises TypeError: If the object is not a timeseries or a float
        :return: The Timeseries where a scalar or another Timeseries are subtract to all numeric columns
        :rtype: Timeseries
        """
        if isinstance(other, int | float):
            df = self.timeseries.with_columns(pl.selectors.numeric().sub(other))
        elif isinstance(other, Timeseries):
            if self.frequency < other.frequency:
                other.upsample(self.frequency)
            elif self.frequency > other.frequency:
                self.upsample(other.frequency)
            df = (
                self._join(
                    other=other,
                    how="full",
                )
                .fill_null(0)
                .with_columns(pl.col("value").sub(pl.col("value_right")).alias("value"))
                .select("time", "value")
            )
        else:
            raise TypeError("Timeseries can't perform subtraction")

        return Timeseries(df, self.timezone)

    def __truediv__(self, other: float | Timeseries) -> Timeseries:
        """Divide all numeric columns by a scalar or timeseries.

        :raises TypeError: If the object is not a timeseries or a float
        :return: The Timeseries where all numeric columns are divided by a scalar or another Timeseries
        :rtype: Timeseries
        """
        if isinstance(other, int | float):
            if other == 0:
                raise ZeroDivisionError("Division by zero is not allowed")
            df = self.timeseries.with_columns(pl.selectors.numeric().truediv(other))
        elif isinstance(other, Timeseries):
            if self.frequency < other.frequency:
                other.upsample(self.frequency)
            elif self.frequency > other.frequency:
                self.upsample(other.frequency)
            df = (
                self._join(
                    other=other,
                    how="full",
                )
                .fill_null(1)
                .with_columns(pl.col("value").truediv(pl.col("value_right")).alias("value"))
                .select("time", "value")
            )
        else:
            raise TypeError("Timeseries can't be divided")

        return Timeseries(df, self.timezone)

    @property
    def dataframe(self) -> pl.DataFrame:
        """Returns the Timeseries DataFrame"""
        return self.timeseries

    @property
    def shape(self) -> tuple[int, int]:
        """Returns the Timeseries shape"""
        return self._get_shape()

    @property
    def index(self) -> list[datetime]:
        """Returns the Timeseries indexes"""
        return self.timeseries.select("time").to_series().to_list()

    @property
    def timestep(self) -> pendulum.Duration | None:
        """Return the frequency string of the timeseries index."""
        return self.frequency

    def remove_na(self, inplace: bool = True) -> Timeseries:
        """
        Remove rows containing null values.

        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: The cleaned Timeseries
        :rtype: Timeseries
        """
        df = self.timeseries.drop_nulls()
        return self._return_inplace(df, inplace)

    def to_frame(self, engine: Literal["polars", "pandas"] = "polars") -> pl.DataFrame | pd.DataFrame:
        """
        Return the internal time series as a data frame.

        :param engine: The engine to use for the output, defaults to "pandas"
        :type engine: str, optional
        :return: The internal Timeseries data
        :rtype: pl.DataFrame or pd.DataFrame
        """
        if engine == "pandas":
            return self.timeseries.to_pandas()
        if engine == "polars":
            return self.timeseries
        raise ValueError("Unsupported engine. Use 'polars' or 'pandas'.")

    def to_lazy(self) -> pl.LazyFrame:
        """
        Convert the internal Polars DataFrame to a LazyFrame.

        :return: A Polars LazyFrame representation of the Timeseries
        :rtype: pl.LazyFrame
        """
        return self.timeseries.lazy()

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

    def reset_index(
        self,
        index: list[datetime | pendulum.DateTime | str],
        date_format: str = "YYYY-MM-DD HH:mm:ss z",
        inplace: bool = True,
    ) -> Timeseries:
        """Reset the Timeseries index using a list of new indexes.

        :param index: New indexes to use for the Timeseries. Should be datetime or string representation of datetimes
        :type index: list[str  |  datetime]
        :param date_format: _description_, defaults to "YYYY-MM-DD HH:mm:ss z"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: The Timeseries with new indexes.
        :rtype: Timeseries
        """
        index = [build_datetime(i, date_format=date_format).in_tz(self.timezone) for i in index]

        new_df = pl.DataFrame({"time": index, "value": [None] * len(index)}).with_columns(
            pl.col("time").cast(pl.Datetime("us", time_zone=self.timezone))
        )

        df = (
            Timeseries(
                pl.concat([self.timeseries, new_df], how="vertical").sort("time"),
                timezone=self.timezone,
                interpolation_method=self.interpolation_method,
            )
            .interpolate()
            .filter(index)
            .dataframe
        )

        return self._return_inplace(df, inplace)

    def _get_shape(self) -> tuple[int, int]:
        """Return (rows, columns) of the underlying Polars DataFrame."""
        return self.timeseries.shape

    def set_timezone(self, timezone: str) -> None:
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

    def set_interpolation_method(self, interpolation_method: Literal["constant", "linear"] = "constant") -> None:
        """
        Set the interpolation method for the Timeseries.

        :param interpolation_method: The interpolation method to use, either "linear" or "constant".
        :type interpolation_method: Literal["constant", "linear"]
        """
        self._check_interpolation_method(interpolation_method)
        self.interpolation_method = interpolation_method

    def sort(
        self,
        inplace: bool = True,
        descending: bool = False,
    ) -> Timeseries:
        """
        Sort the Timeseries by the given variable(s).

        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :param descending: Sort in descending order, defaults to False
        :type descending: bool, optional
        :return: Sorted Timeseries
        :rtype: Timeseries
        """
        df = self.timeseries.sort("time", descending=descending)
        return self._return_inplace(df, inplace)

    def set_value(
        self,
        time: datetime | str,
        value: float | None,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Set or update a value at a specific datetime. If the datetime exists, it is overwritten.

        :param time: Datetime to set
        :type time: datetime or str
        :param value: Value to set
        :type value: float or int
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Timeseries with the added value
        :rtype: Timeseries
        """
        dt: pendulum.DateTime = build_datetime(time, date_format).in_tz(self.timezone)

        if len(self.timeseries) == 0:
            df = pl.DataFrame({"time": [dt], "value": [value]}).with_columns(
                pl.col("time").dt.replace_time_zone(self.timezone),
                pl.col("value").cast(pl.Float64()),
            )
            if inplace:
                self.timeseries = df
                return self

            return Timeseries(df, self.timezone)

        df = self.timeseries.filter(pl.col("time") != dt)
        new_row = pl.DataFrame({"time": [dt], "value": [value]}).with_columns(
            pl.col("time").cast(pl.Datetime("us", time_zone=self.timezone)),
            pl.col("value").cast(pl.Float64()),
        )
        df = pl.concat([df, new_row]).sort("time")

        return self._return_inplace(df, inplace)

    def upsample(
        self,
        frequency: str | pendulum.Duration,
        inplace: bool = True,
    ) -> Timeseries:
        """
        Upsample the Timeseries to a higher frequency.

        Fills in missing timestamps by interpolating or forward-filling values.

        :param frequency: Frequency string (e.g., "15m", "1h") defining the new time resolution
        :type frequency: str | pendulum.Duration
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :param strategy: Method to fill missing values: "linear" for interpolation, "constant" for forward fill
        :type strategy: str, optional
        :raises NotImplementedError: If the provided strategy is not supported
        :return: Upsampled Timeseries
        :rtype: Timeseries
        """

        if self.interpolation_method == "linear":
            df = (
                self.timeseries.upsample(time_column="time", every=frequency)
                .with_columns(pl.col("value").interpolate_by("time"))
                .fill_null(strategy="forward")
                .sort("time")
            )
        elif self.interpolation_method == "constant":
            df = (
                self.timeseries.upsample(time_column="time", every=frequency)
                .fill_null(
                    strategy="forward",
                )
                .sort("time")
            )

        return self._return_inplace(df, inplace)

    def groupby(
        self,
        granularity: str | timedelta,
        agg: Literal["mean", "sum", "min", "max"] = "mean",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Group the Timeseries dynamically by time intervals.

        :param granularity: Grouping interval (e.g., "1h", "1d")
        :type granularity: str or timedelta
        :param agg: Aggregation method, defaults to "mean"
        :type agg: Literal["mean", "sum", "min", "max"], optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises NotImplementedError: If the aggregation function is unsupported
        :return: Grouped Timeseries
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

        return self._return_inplace(df, inplace)

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
        :return: Deduplicated Timeseries
        :rtype: Timeseries
        """
        df = self.timeseries.unique(subset=variables, maintain_order=True)
        return self._return_inplace(df, inplace)

    def _join(
        self,
        other: Timeseries | pl.DataFrame,
        by: str = "time",
        how: Literal["inner", "left", "right", "full", "semi", "anti", "cross", "outer"] = "inner",
        suffixes: str = "_right",
    ) -> pl.DataFrame:
        """
        Merge this Timeseries with another.

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
        :return: Merged Timeseries
        :rtype: Timeseries
        """
        if isinstance(other, Timeseries):
            other = other.timeseries
        return self.timeseries.join(other, on=by, how=how, suffix=suffixes, coalesce=True)

    def to_file(
        self,
        path: str | Path,
        file_format: Literal["csv", "parquet", "pickle"] = "csv",
        separator: str = ";",
    ) -> None:
        """
        Export the Timeseries to a file.

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
            self.timeseries.write_csv(path, separator=separator)
        elif file_format_lower == "parquet":
            self.timeseries.write_parquet(path)
        elif file_format_lower == "pickle":
            with open(path, "wb") as f:
                pickle.dump(self, f)
        else:
            raise NotImplementedError("Format not supported")

    def filter(
        self,
        item: list[datetime | pendulum.DateTime | str] | datetime | pendulum.DateTime | str,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Filter the Timeseries based on a list of datetime.

        :param item: Datetime to filter the Timeseries
        :type item: list[datetime] or datetime or pendulum.DateTime or str
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss z"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises NotImplementedError: If the times to filter type is unsupported
        :return: Filtered Timeseries
        :rtype: Timeseries
        """
        if isinstance(item, list):
            item = [pendulum.instance(i).in_tz(self.timezone) if isinstance(i, datetime) else i for i in item]
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

        return self._return_inplace(df, inplace)

    def max(self) -> float | None:
        """Return the max value in the 'value' column.

        :return: The Timeseries max value
        :rtype: float or None
        """
        if "value" in self.timeseries.columns and len(self.timeseries) > 0:
            return cast("float", self.timeseries["value"].max())
        return None

    def min(self) -> float | None:
        """Return the min value in the 'value' column.

        :return: The Timeseries min value
        :rtype: float or None
        """
        if "value" in self.timeseries.columns and len(self.timeseries) > 0:
            return cast("float", self.timeseries["value"].min())
        return None

    def interpolate(self, inplace: bool = True) -> Timeseries:
        """Interpolate the Timeseries to fill in missing values.

        :param method: Interpolation method, defaults to "constant"
        :type method: Literal["linear", "constant"], optional
        :param inplace: Whether to modify the current instance, defaults to False
        :type inplace: bool, optional
        :raises NotImplementedError: If the method is not supported
        :return: Interpolated Timeseries
        :rtype: Timeseries
        """
        if self.interpolation_method == "linear":
            df = self.timeseries.with_columns(pl.col("value").interpolate_by("time"))
        elif self.interpolation_method == "constant":
            df = self.timeseries.fill_null(strategy="forward")
        else:
            raise NotImplementedError("Unsupported interpolation method, use 'linear' or 'constant'")

        return self._return_inplace(df, inplace)

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
        :return: Dictionary with time and value
        :rtype: dict
        """
        if len(self.timeseries) == 0:
            return None
        dt = build_datetime(datetime, date_format).in_tz(self.timezone)
        if dt > self.timeseries["time"].max():  # type: ignore[operator]
            return None

        df: pl.DataFrame = self.filter(datetime, date_format, inplace=False).dataframe
        if len(df) > 0:
            return df.to_dicts()[0]["value"]

        df = (
            self.set_value(datetime, None, date_format, inplace=False)  # type: ignore[assignment]
            .interpolate(inplace=False)
            .filter(datetime, date_format, inplace=False)
            .dataframe
        )
        if len(df) > 0:
            return df.to_dicts()[0]["value"]
        return None

    def plot(
        self,
        title: str = "Time Series Plot",
        height: int = 500,
        width: int = 800,
        show_grid: bool = True,
        line_color: str = "#1f77b4",
        line_shape: Literal["hv", "linear", "spline"] = "hv",
        template: str = "plotly_white",
    ) -> plotly.graph_objects.Figure:
        """
        Generate a Plotly figure for the Timeseries data.

        :param title: Plot title, defaults to "Time Series Plot"
        :type title: str, optional
        :param height: Plot height in pixels, defaults to 500
        :type height: int, optional
        :param width: Plot width in pixels, defaults to 800
        :type width: int, optional
        :param show_grid: Whether to show grid lines, defaults to True
        :type show_grid: bool, optional
        :param line_color: Color of the line plot, defaults to "#1f77b4" (Plotly default blue)
        :type line_color: str, optional
        :param line_shape: Shape of the plot, defaults to "hv"
        :type line_shape: Literal["hv", "linear", "spline"], optional
        :param template: Plotly template to use, defaults to "plotly_white"
        :type template: str, optional
        :return: Plotly figure object
        :rtype: plotly.graph_objects.Figure
        """
        # Create the figure using Plotly Express
        fig = px.line(
            self.timeseries,
            x="time",
            y=self.timeseries.select(pl.selectors.numeric()).columns,
            title=title,
            height=height,
            width=width,
            template=template,
            line_shape=line_shape,
            color_discrete_sequence=[line_color] if line_color else None,
        )

        # Update layout for grid settings
        fig.update_layout(
            hovermode="x unified",
            xaxis={
                "showgrid": show_grid,
                "gridcolor": "lightgray" if show_grid else None,
            },
            yaxis={
                "showgrid": show_grid,
                "gridcolor": "lightgray" if show_grid else None,
            },
        )

        return fig

    def _return_inplace(self, df: pl.DataFrame, inplace: bool) -> Timeseries:
        """
        Return the Timeseries object itself or modify existing.

        :return: The Timeseries object
        :rtype: Timeseries
        """
        if inplace:
            self.timeseries = df.sort("time")
            self.frequency = infer_frequency()
            return self
        return Timeseries(df, self.timezone)
