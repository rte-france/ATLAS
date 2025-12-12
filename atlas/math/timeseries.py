"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

This module provides a Timeseries class for handling Timeseries data using Polars.
"""

from __future__ import annotations

import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd
import pendulum
import plotly
import plotly.express as px
import plotly.graph_objects
import polars as pl

import atlas.config as cfg
from atlas.io_utils.utils import get_metadata_from_frame, read_data_file
from atlas.timing import build_datetime, check_timezone, generate_datetimes, get_duration, infer_frequency


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
        timeseries: pl.DataFrame | Timeseries | pd.DataFrame | dict[str, list[float]] | None = None,
        timezone: str = "UTC",
    ) -> None:
        """
        :param timeseries: The input Timeseries data.
        :type timeseries: pl.DataFrame or Timeseries
        :param timezone: Timezone string used to convert datetime values, defaults to "UTC"
        :type timezone: str, optional
        """
        check_timezone(timezone)
        self.timezone: str = timezone

        self._check_timeseries(timeseries)
        self._set_timeseries(timeseries, timezone)

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        filters: tuple[str, str] | None = None,
        separator: str = ";",
    ) -> Timeseries:
        """
        Load a Timeseries object from a file.

        :param file_path: Path to the file
        :type file_path: str or Path
        :param timezone: Timezone string used to convert datetime values, defaults to "UTC"
        :type timezone: str, optional
        :param filters: Filters columns, defaults to ";"
        :type filters: tuple[str, str] or None, optional
        :param separator: Export column separator format, defaults to ";"
        :type separator: str, optional
        :raises ValueError: If file format is not supported
        :return: Loaded Timeseries object
        :rtype: Timeseries
        """

        return cls(read_data_file(file_path, filters, separator), timezone)

    @classmethod
    def from_values(
        cls,
        start_date: str | datetime | pendulum.DateTime,
        frequency: str | pendulum.Duration,
        values: list[float],
        date_format="YYYY-MM-DD HH:mm:ss",
        timezone: str = "UTC",
    ) -> Timeseries:
        """
        Create a Timeseries from start date, frequency and a list of values.

        :param start_date: Start date of the timeseries
        :type start_date: str or datetime or pendulum.DateTime
        :param frequency: Frequency of the timeseries (e.g., "1h", "15m")
        :type frequency: str or pendulum.Duration
        :param values: List of values corresponding to the time intervals
        :type values: list[float]
        :param timezone: Timezone string, defaults to "UTC"
        :type timezone: str, optional
        :raises ValueError: If file there is no value to insert in the Timeseries
        :return: A Timeseries object with the specified parameters
        :rtype: Timeseries
        """
        if len(values) < 2:
            raise ValueError("Timeseries must contains at least 2 values")

        start = build_datetime(start_date, date_format).in_tz(timezone)
        end = build_datetime(start + (len(values) - 1) * get_duration(frequency)).in_tz(timezone)

        datetimes = generate_datetimes(start, end, frequency, timezone)

        df = pl.DataFrame(
            {"time": datetimes, "value": values},
            schema={"time": pl.Datetime("us", time_zone=timezone), "value": pl.Float64()},
        )

        return cls(df, timezone)

    @classmethod
    def from_index(
        cls,
        start_date: str | datetime | pendulum.DateTime,
        frequency: str | pendulum.Duration,
        end_date: str | datetime | pendulum.DateTime,
        default_value: list[float] | float = 0,
        date_format="YYYY-MM-DD HH:mm:ss",
        timezone: str = "UTC",
    ) -> Timeseries:
        """
        Create a Timeseries from a time range and a default value or list of values.

        :param start_date: Start date of the timeseries
        :type start_date: str or datetime or pendulum.DateTime
        :param frequency: Frequency of the timeseries (e.g., "1h", "15m")
        :type frequency: str or pendulum.Duration
        :param end_date: End date of the timeseries
        :type end_date: str or datetime or pendulum.DateTime
        :param default_value: A scalar value or a list of values to fill the timeseries
        :type default_value: list[float] or float, optional
        :param date_format: Format to interpret date strings, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param timezone: Timezone string, defaults to "UTC"
        :type timezone: str, optional
        :raises ValueError: If default_value is a list with length mismatch
        :return: A Timeseries object with the specified index and values
        :rtype: Timeseries
        """

        start = build_datetime(start_date, date_format).in_tz(timezone)
        end = build_datetime(end_date, date_format).in_tz(timezone)

        datetimes = generate_datetimes(start, end, frequency, timezone)

        if isinstance(default_value, list):
            if len(default_value) != len(datetimes):
                raise ValueError(
                    f"Values  passed is of size {len(default_value)} when datetimes generated is of size {len(datetimes)}"
                )
            else:
                df = pl.DataFrame(
                    {"time": datetimes, "value": default_value},
                    schema={"time": pl.Datetime("us", time_zone=timezone), "value": pl.Float64()},
                )
        elif isinstance(default_value, float | int):
            df = pl.DataFrame(
                {"time": datetimes, "value": [default_value] * len(datetimes)},
                schema={"time": pl.Datetime("us", time_zone=timezone), "value": pl.Float64()},
            )

        return cls(df, timezone)

    @classmethod
    def from_timeseries(cls, timeseries: Timeseries, default_value: float | None = None) -> Timeseries:
        """Create a Timeseries from another, using its structure.

        :param timeseries: The input timeseries object
        :type timeseries: Timeseries
        :param default_value: default value to pass to all timestamp values, defaults to None
        :type default_value: float | None, optional
        :return: The timeseries object instantiated
        :rtype: Timeseries
        """

        if not isinstance(timeseries, Timeseries):
            raise TypeError("Input has to be a timeseries object, if using a dataframe, use 'from_dataframe' ")
        if default_value is not None:
            df = timeseries.dataframe.with_columns(pl.lit(default_value).alias("value"))
            return cls(df, timezone=timeseries.timezone)
        else:
            return cls(timeseries)

    @classmethod
    def from_dataframe(
        cls,
        dataframe: pl.DataFrame | pd.DataFrame,
        timezone="UTC",
    ) -> Timeseries:
        """Create a Timeseries object from a dataframe-like object.

        :param dataframe: The input dataframe
        :type dataframe: pl.DataFrame | Timeseries | pd.DataFrame | dict[str, list[float]]
        :param timezone: The timezone of the Timeseries, defaults to "UTC"
        :type timezone: str, optional
        :return: The timeseries instantiated from the dataframe-like object
        :rtype: Timeseries
        """
        if not isinstance(dataframe, pl.DataFrame | pd.DataFrame):
            raise TypeError("Input has to be a dataframe-like object.")

        return cls(dataframe, timezone)

    def describe(self) -> dict[str, Any]:
        """
        Get metadata about the timeseries.

        :return: A dictionary containing timeseries metadata
        :rtype: dict[str, Any]
        """
        return get_metadata_from_frame(self.timeseries)

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

            if len(self.timeseries) == 2 and infer_frequency(self.timeseries) > pendulum.duration(days=1):
                self.upsample("1h", interpolation_method="linear")

            self.sort()

            self.frequency: pendulum.Duration = infer_frequency(self.timeseries)

    def __getitem__(self, column_name: str) -> list[float | datetime]:
        if column_name not in ("time", "value"):
            raise KeyError("Column name has to be either time or value")
        else:
            return self.dataframe[column_name].to_list()

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

    def __contains__(self, item: datetime | str | pendulum.DateTime) -> bool:
        """Check if a temporal index exists in the Timeseries.

        :param item: Datetime to check for existence
        :type item: datetime or str or pendulum.DateTime
        :return: True if the datetime exists in the Timeseries index, False otherwise
        :rtype: bool
        """
        try:
            dt = build_datetime(item).in_tz(self.timezone)
            return self.timeseries.filter(pl.col("time") == dt).height > 0
        except Exception:
            return False

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
                other = other.upsample(self.frequency, inplace=False)
                my_ts = Timeseries(self)
            elif self.frequency > other.frequency:
                my_ts = self.upsample(other.frequency, inplace=False)
            else:
                my_ts = Timeseries(self)

            df = (
                my_ts._join(
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
                other = other.upsample(self.frequency, inplace=False)
                my_ts = Timeseries(self)
            elif self.frequency > other.frequency:
                my_ts = self.upsample(other.frequency, inplace=False)
            else:
                my_ts = Timeseries(self)

            df = (
                my_ts._join(
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
                other = other.upsample(self.frequency, inplace=False)
                my_ts = Timeseries(self)
            elif self.frequency > other.frequency:
                my_ts = self.upsample(other.frequency, inplace=False)
            else:
                my_ts = Timeseries(self)

            df = (
                my_ts._join(
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
                other = other.upsample(self.frequency, inplace=False)
                my_ts = Timeseries(self)
            elif self.frequency > other.frequency:
                my_ts = self.upsample(other.frequency, inplace=False)
            else:
                my_ts = Timeseries(self)

            df = (
                my_ts._join(
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
    def values(self) -> list[float]:
        """Returns the Timeseries values"""
        return self.timeseries.select("value").to_series().to_list()

    @property
    def timestep(self) -> pendulum.Duration | None:
        """Return the frequency string of the timeseries index."""
        return self.frequency

    @property
    def metadata(self) -> dict[str, Any]:
        """Return the metadata of the timeseries."""
        return self.describe()

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

    def _get_shape(self) -> tuple[int, int]:
        """Return (rows, columns) of the underlying Polars DataFrame."""
        return self.timeseries.shape

    def set_timezone(self, timezone: str) -> None:
        """
        Convert the datetime column to a new timezone.

        :param timezone: Timezone string
        :type timezone: str
        """
        check_timezone(timezone)

        self.timezone = timezone
        self.timeseries = self.timeseries.with_columns(
            pl.col("time").dt.convert_time_zone(timezone),
        )

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
            return self._return_inplace(df, inplace)

        df = self.timeseries.filter(pl.col("time") != dt)
        new_row = pl.DataFrame({"time": [dt], "value": [value]}).with_columns(
            pl.col("time").cast(pl.Datetime("us", time_zone=self.timezone)),
            pl.col("value").cast(pl.Float64()),
        )
        df = pl.concat([df, new_row]).sort("time")

        return self._return_inplace(df, inplace)

    def add_value_at(
        self,
        time: datetime | str,
        value: float,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Set or add to an existing value at a specific datetime.

        :param time: Datetime to set
        :type time: datetime or str
        :param value: Value to set
        :type value: float
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Timeseries with the added value
        :rtype: Timeseries
        """
        try:
            current = self.get_value(time)
            return self.set_value(time, value + (current if current is not None else 0), date_format, inplace)
        except (KeyError, ValueError):
            return self.set_value(time, value, date_format, inplace)
        except BaseException as e:
            cfg.logger.error(e)
            return self

    def upsample(
        self,
        frequency: str | pendulum.Duration,
        interpolation_method: Literal["linear", "constant"] = "constant",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Upsample the Timeseries to a higher frequency.

        Fills in missing timestamps by interpolating or forward-filling values.

        :param frequency: Frequency string (e.g., "15m", "1h") defining the new time resolution
        :type frequency: str | pendulum.Duration
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :param interpolation_method: Method to fill missing values: "linear" for interpolation, "constant" for forward fill
        :type interpolation_method: str, optional
        :raises NotImplementedError: If the provided interpolation_method is not supported
        :return: Upsampled Timeseries
        :rtype: Timeseries
        """

        if interpolation_method == "linear":
            df = (
                self.timeseries.upsample(time_column="time", every=frequency)
                .with_columns(pl.col("value").interpolate_by("time"))
                .fill_null(strategy="forward")
                .sort("time")
            )
        elif interpolation_method == "constant":
            df = (
                self.timeseries.upsample(time_column="time", every=frequency)
                .fill_null(
                    strategy="forward",
                )
                .sort("time")
            )
        else:
            raise NotImplementedError("Unsupported interpolation method")

        return self._return_inplace(df, inplace)

    def groupby(
        self,
        frequency: str | pendulum.Duration,
        agg: Literal["mean", "sum", "min", "max"] = "mean",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Group the Timeseries dynamically by time intervals.

        :param frequency: Grouping interval (e.g., "1h", "1d")
        :type frequency: str or pendulum.Duration
        :param agg: Aggregation method, defaults to "mean"
        :type agg: Literal["mean", "sum", "min", "max"], optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises NotImplementedError: If the aggregation function is unsupported
        :return: Grouped Timeseries
        :rtype: Timeseries
        """
        grouped_df = self.timeseries.group_by_dynamic("time", every=frequency)
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

    def set_frequency(self, frequency: str | pendulum.Duration, inplace: bool = True) -> Timeseries:
        """
        Change the frequency (timestep) of the time series.

        :param frequency: The desired frequency. Can be a string (e.g., '1d', '15m') or a `pendulum.Duration`.
        :type frequency: str or pendulum.Duration
        :param inplace: If True, modifies the object in place. If False, returns a new modified object.
        :type inplace: bool
        :return: The resampled time series, either modified in place or as a new object.
        :rtype: Timeseries
        """
        new_timestep = get_duration(frequency)

        if new_timestep > self.frequency:
            df = self.groupby(new_timestep, inplace=False)
        elif new_timestep < self.frequency:
            df = self.upsample(new_timestep, inplace=False)
        else:
            df = self

        return self._return_inplace(df.dataframe, inplace)

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
        :return: Merged Timeseries
        :rtype: Timeseries
        """
        if isinstance(other, Timeseries):
            other = other.dataframe
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
        :param separator: Export column separator format, defaults to ";"
        :type separator: str, optional
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

    def to_file_with_attribute(
        self,
        path: str | Path,
        attribute: str,
        file_format: Literal["csv", "parquet", "pickle"] = "csv",
        separator: str = ";",
        concatenate: bool = True,
    ) -> None:
        """
        Export the Timeseries to a file with an attribute column.

        If the file already exists and concatenate is True, the new data will be
        appended to the existing data.

        :param path: Destination file path
        :type path: str or Path
        :param attribute: Attribute name to add as a column
        :type attribute: str
        :param file_format: Export file format, defaults to "csv"
        :type file_format: Literal["csv", "parquet", "pickle"], optional
        :param separator: Export column separator format, defaults to ";"
        :type separator: str, optional
        :param concatenate: If True, concatenate with existing file data, defaults to True
        :type concatenate: bool, optional
        :raises ValueError: If file extension doesn't match format
        :raises NotImplementedError: If the file format is not supported
        """
        file_format_lower = file_format.lower()

        if isinstance(path, Path):
            path_str = str(path)
        else:
            path_str = path

        if not path_str.lower().endswith(file_format_lower):
            raise ValueError("Format and file extension don't match.")

        df_to_write = self.timeseries.insert_column(1, pl.lit(attribute).alias("attribute"))

        if concatenate:
            path_obj = Path(path_str)
            if path_obj.exists() and file_format_lower != "pickle":
                try:
                    if file_format_lower == "csv":
                        existing_df = pl.read_csv(path_str, separator=separator)
                    elif file_format_lower == "parquet":
                        existing_df = pl.read_parquet(path_str)

                    # Concatenate with existing data
                    df_to_write = pl.concat([existing_df, df_to_write])
                except Exception as e:
                    cfg.logger.warning(f"Could not read existing file for concatenation: {e}")

        # Write the file
        if file_format_lower == "csv":
            df_to_write.write_csv(path_str, separator=separator)
        elif file_format_lower == "parquet":
            df_to_write.write_parquet(path_str)
        elif file_format_lower == "pickle":
            with open(path_str, "wb") as f:
                pickle.dump(self, f)
        else:
            raise NotImplementedError("Format not supported")

    def filter(
        self,
        item: list[datetime] | list[pendulum.DateTime] | list[str] | datetime | pendulum.DateTime | str,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Filter the Timeseries based on a list of datetime.

        :param item: Datetime to filter the Timeseries
        :type item: list[datetime] or datetime or pendulum.DateTime or str
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises NotImplementedError: If the times to filter type is unsupported
        :return: Filtered Timeseries
        :rtype: Timeseries
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

        return self._return_inplace(df, inplace)

    def slice(
        self,
        start_bound: datetime | pendulum.DateTime | str,
        end_bound: datetime | pendulum.DateTime | str,
        closed: Literal["left", "right", "both", "none"] = "both",
        inplace: bool = True,
    ) -> Timeseries:
        """Get a slice of the Timeseries

        :param start_bound: Datetime to filter the Timeseries
        :param end_bound: Datetime to filter the Timeseries
        :param closed : {'both', 'left', 'right', 'none'}
            Define which sides of the interval are closed (inclusive).
        :param inplace: Whether to modify the current instance, defaults to True
        :return: The Timeseries object
        """
        date_start = build_datetime(start_bound).in_tz(self.timezone)
        date_end = build_datetime(end_bound).in_tz(self.timezone)
        df = self.timeseries.filter(pl.col("time").is_between(date_start, date_end, closed))

        return self._return_inplace(df, inplace)

    def slice_with_offset(
        self,
        offset: int,
        length: int | None = None,
        inplace: bool = True,
    ) -> Timeseries:
        """Get a slice of the Timeseries

        :param offset: Start index. Negative indexing is supported.
        :param length: Length of the slice. If set to `None`, all rows starting at the offset will be selected.
        :param inplace: Whether to modify the current instance, defaults to True
        :return: The Timeseries object
        """
        df = self.timeseries.slice(offset, length)
        return self._return_inplace(df, inplace)

    def max(self) -> float:  # type:ignore[return]
        """Return the max value in the 'value' column.

        :return: The Timeseries max value
        :rtype: float or None
        """
        if len(self.timeseries) > 0:
            return cast("float", self.timeseries["value"].max())
        else:
            RuntimeError("Timeseries is empty, can't get the maximum value")

    def min(self) -> float:  # type:ignore[return]
        """Return the min value in the 'value' column.

        :return: The Timeseries min value
        :rtype: float or None
        """
        if len(self.timeseries) > 0:
            return cast("float", self.timeseries["value"].min())
        else:
            RuntimeError("Timeseries is empty, can't get the minimum value")

    def sum(self) -> float:  # type:ignore[return]
        """Return the sum of the 'value' column.

        :return: The Timeseries sum value
        :rtype: float or None
        """
        if len(self.timeseries) > 0:
            return cast("float", self.timeseries["value"].sum())
        else:
            RuntimeError("Timeseries is empty, can't perform the sum")

    def abs(self, inplace=True) -> Timeseries:
        """Compute the absolute value of each timestamp

        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: The timeseries with absolute values
        :rtype: Timeseries
        """
        df = self.timeseries.with_columns(pl.col("value").abs())

        return self._return_inplace(df, inplace)

    def interpolate(
        self, interpolation_method: Literal["linear", "constant"] = "constant", inplace: bool = True
    ) -> Timeseries:
        """Interpolate the Timeseries to fill in missing values.

        :param interpolation_method: Interpolation method, defaults to "constant"
        :type interpolation_method: Literal["linear", "constant"], optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises NotImplementedError: If the method is not supported
        :return: Interpolated Timeseries
        :rtype: Timeseries
        """
        if interpolation_method == "linear":
            df = self.timeseries.with_columns(pl.col("value").interpolate_by("time"))
        elif interpolation_method == "constant":
            df = self.timeseries.fill_null(strategy="forward")
        else:
            raise NotImplementedError("Unsupported interpolation method, use 'linear' or 'constant'")

        return self._return_inplace(df, inplace)

    def get_value(
        self,
        datetime: str | datetime | pendulum.DateTime,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
    ) -> float:
        """Return values at the given datetime. If exact match is not found, interpolate.

        :param datetime: Datetime to get value for
        :type datetime: str or datetime
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :return: The value at the timestamp requested
        :rtype: float
        """
        if len(self.timeseries) == 0:
            raise ValueError("Can't get value on empty timeseries.")
        dt = build_datetime(datetime, date_format).in_tz(self.timezone)

        df: pl.DataFrame = self.filter(datetime, date_format, inplace=False).dataframe
        if len(df) > 0:
            return df.to_dicts()[0]["value"]
        else:
            raise KeyError(f"Value for {dt.to_datetime_string()} not found in the Timeseries.")

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
            self.frequency = infer_frequency(self.timeseries)
            return self
        return Timeseries(df, self.timezone)

    def first_date(self) -> pendulum.DateTime | None:
        """
        Return the first date in the Timeseries index.

        :return: The first date in the Timeseries index
        :rtype: DateTime or None
        """
        if len(self.timeseries) > 0:
            return cast(pendulum.DateTime, pendulum.instance(self.timeseries.select("time").head(1).item()))
        return None

    def last_date(self) -> pendulum.DateTime | None:
        """
        Return the last date in the Timeseries index.

        :return: The last date in the Timeseries index
        :rtype: DateTime or None
        """
        if len(self.timeseries) > 0:
            return cast(pendulum.DateTime, pendulum.instance(self.timeseries.select("time").tail(1).item()))
        return None
