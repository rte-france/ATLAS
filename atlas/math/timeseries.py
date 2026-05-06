"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

This module provides a Timeseries class for handling Timeseries data using Polars.
"""

from __future__ import annotations

import pickle
from collections.abc import Generator, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd
import pendulum
import plotly
import plotly.express as px
import plotly.graph_objects
import polars as pl

from atlas.io_utils.utils import get_metadata_from_frame, read_data_file
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.timing import build_datetime, check_timezone, generate_datetimes, get_duration, infer_frequency
from atlas.type import TimeseriesDict


class Timeseries(AbstractTimeseries[pl.DataFrame]):
    """
    A flexible and efficient time series class using a Polars backend.

    The Timeseries class provides a unified interface for handling, analyzing, and visualizing
    time series data. It supports a variety of input formats (Polars DataFrame, Pandas DataFrame,
    dictionary, or another Timeseries instance) and ensures robust handling of time zones and
    interpolation methods.
    """

    def __init__(
        self,
        timeseries: pl.DataFrame | Timeseries | pd.DataFrame | TimeseriesDict | None = None,
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
        frequency: str | timedelta | pendulum.Duration,
        values: Sequence[float] | pd.Series,
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
        frequency: str | timedelta | pendulum.Duration,
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
    def from_timeseries(cls, timeseries: AbstractTimeseries, default_value: float | None = None) -> Timeseries:
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
        :type dataframe: pl.DataFrame | Timeseries | pd.DataFrame
        :param timezone: The timezone of the Timeseries, defaults to "UTC"
        :type timezone: str, optional
        :return: The timeseries instantiated from the dataframe-like object
        :rtype: Timeseries
        """
        if not isinstance(dataframe, pl.DataFrame | pd.DataFrame | dict):
            raise TypeError("Input has to be a dataframe-like object.")

        return cls(dataframe, timezone)

    def describe(self) -> dict[str, Any]:
        """
        Get metadata about the timeseries.

        :return: A dictionary containing timeseries metadata
        :rtype: dict[str, Any]
        """
        return get_metadata_from_frame(self.timeseries)

    def _check_timeseries(self, timeseries: pl.DataFrame | Timeseries | pd.DataFrame | TimeseriesDict | None) -> None:
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
        timeseries: pl.DataFrame | Timeseries | pd.DataFrame | TimeseriesDict | None,
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
            self.frequency = infer_frequency(self.timeseries)
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

            self._return(self.timeseries, inplace=True)

    def _get_data(self) -> pl.DataFrame:
        """Return the underlying DataFrame."""
        return self.timeseries

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

        :param other: Other timeseries or scalar to multiply the value of he current Timeseries
        :type other: float | Timeseries
        :raises TypeError: If the object is not a timeseries or a float
        :raises ValueError: If operation could not be done
        :return: The Timeseries where all numeric columns are multiplied by a scalar or another Timeseries
        :rtype: Timeseries
        """
        if isinstance(other, int | float):
            df = self.timeseries.with_columns(pl.selectors.numeric().mul(other))
        elif isinstance(other, Timeseries):
            if self.frequency != other.frequency:
                raise ValueError("Could not perform multiplication on Timeseries because frequencies don't match")
            elif not other.dataframe["time"].is_in(self.dataframe["time"]).all():
                raise ValueError(
                    "Could not perform multiplication on Timeseries because indexes of Timeseries to add "
                    "are not in current Timeseries"
                )
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

        :param other: Other timeseries or scalar to add to value of the current Timeseries
        :type other: float | Timeseries
        :raises TypeError: If the object is not a timeseries or a float
        :raises ValueError: If operation could not be done
        :return: The Timeseries where a scalar or another Timeseries are added to all numeric columns
        :rtype: Timeseries
        """
        if isinstance(other, int | float):
            df = self.timeseries.with_columns(pl.selectors.numeric().add(other))
        elif isinstance(other, Timeseries):
            if self.frequency != other.frequency:
                raise ValueError("Could not perform addition on Timeseries because frequencies don't match")
            elif not other.dataframe["time"].is_in(self.dataframe["time"]).all():
                raise ValueError(
                    "Could not perform addition on Timeseries because indexes of Timeseries to add are "
                    "not in current Timeseries"
                )
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

        :param other: Other timeseries or scalar to subtract to the value the current Timeseries
        :type other: float | Timeseries
        :raises TypeError: If the object is not a timeseries or a float
        :raises ValueError: If operation could not be done
        :return: The Timeseries where a scalar or another Timeseries are subtract to all numeric columns
        :rtype: Timeseries
        """
        if isinstance(other, int | float):
            df = self.timeseries.with_columns(pl.selectors.numeric().sub(other))
        elif isinstance(other, Timeseries):
            if self.frequency != other.frequency:
                raise ValueError("Could not perform subtraction on Timeseries because frequencies don't match")
            elif not other.dataframe["time"].is_in(self.dataframe["time"]).all():
                raise ValueError(
                    "Could not perform subtraction on Timeseries because indexes of Timeseries to add are "
                    "not in current Timeseries"
                )
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

        :param other: Other timeseries or scalar to divide to the value the current Timeseries
        :type other: float | Timeseries
        :raises TypeError: If the object is not a timeseries or a float
        :raises ValueError: If operation could not be done
        :return: The Timeseries where all numeric columns are divided by a scalar or another Timeseries
        :rtype: Timeseries
        """
        if isinstance(other, int | float):
            if other == 0:
                raise ZeroDivisionError("Division by zero is not allowed")
            df = self.timeseries.with_columns(pl.selectors.numeric().truediv(other))
        elif isinstance(other, Timeseries):
            if self.frequency != other.frequency:
                raise ValueError("Could not perform division on Timeseries because frequencies don't match")
            elif not other.dataframe["time"].is_in(self.dataframe["time"]).all():
                raise ValueError(
                    "Could not perform division on Timeseries because indexes of Timeseries to add are "
                    "not in current Timeseries"
                )
            elif (other.dataframe["value"] == 0).any():
                raise ValueError("Could not perform division on Timeseries because zero values are present")
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
    def timestep(self) -> pendulum.Duration:
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

    def collect(self) -> Timeseries:
        """
        Return self (no-op for eager Timeseries).

        :return: Self
        :rtype: Timeseries
        """
        return self

    def sort(
        self,
        inplace: bool = True,
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
        return self._return(self.timeseries, inplace)

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
        self._invalidate_cache()

    def set_value(
        self,
        time: datetime | str,
        value: float | None,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Update a value at a specific datetime.

        :param time: Datetime to set
        :type time: datetime or str
        :param value: Value to set
        :type value: float or int
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises ValueError: If the time is not in the Timeseries
        :return: Timeseries with the set value
        :rtype: Timeseries
        """
        dt = build_datetime(time, date_format).in_tz(self.timezone)

        if dt not in self.dataframe["time"]:
            raise ValueError(f"Could not set value at {dt} because timestamp is not in the Timeseries")

        df = self.timeseries.with_columns(
            pl.when(pl.col("time") == dt).then(pl.lit(value)).otherwise(pl.col("value")).alias("value")
        )

        return self._return(df, inplace)

    def set_values(
        self,
        other: Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict,
        inplace: bool = True,
    ) -> Timeseries:
        """
        Set or update values. If the datetime exists, it is overwritten.

        :param other: other timeseries with values to updated self
        :type other: Timeseries
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises ValueError: If frequency doesn't match or at least one time of the other Timeseries is not in the
        current one
        :return: Timeseries with the new values
        :rtype: Timeseries
        """
        other = Timeseries(other)
        if len(self.timeseries) == 0:
            other_df = other.dataframe
            return self._return(other_df, inplace)

        other_ts = Timeseries(other)
        if self.frequency != other_ts.frequency:
            raise ValueError("Could not perform set values on Timeseries because frequencies don't match")
        if not other_ts.dataframe["time"].is_in(self.dataframe["time"]).all():
            raise ValueError(
                "Could not set values on Timeseries because indexes to set are not all present in Timeseries"
            )

        df = self.timeseries.filter(~pl.col("time").is_in(other_ts.dataframe["time"]))
        df = pl.concat([df, other_ts.dataframe])

        return self._return(df, inplace)

    def sum_value_at(
        self,
        time: datetime | str,
        value: float,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Add to an existing value at a specific datetime.

        :param time: Datetime to add to the value
        :type time: datetime or str
        :param value: Value to add to the precedent value
        :type value: float
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises ValueError: If time is not present in the Timeseries
        :return: Timeseries with the value added to the precedent value at a specific index
        :rtype: Timeseries
        """
        dt: pendulum.DateTime = build_datetime(time, date_format).in_tz(self.timezone)

        if dt not in self.dataframe["time"]:
            raise ValueError(f"Could not add value at {dt} because timestamp is not in the Timeseries")

        old_value = self.get_value(dt)
        df = self.timeseries.filter(pl.col("time") != dt)
        new_row = pl.DataFrame({"time": [dt], "value": [old_value + value]}).with_columns(
            pl.col("time").cast(pl.Datetime("us", time_zone=self.timezone)),
            pl.col("value").cast(pl.Float64()),
        )
        df = pl.concat([df, new_row])

        return self._return(df, inplace)

    def mul_value_at(
        self,
        time: datetime | str,
        value: float,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Multiply to an existing value at a specific datetime.

        :param time: Datetime to multiply by the value
        :type time: datetime or str
        :param value: Value to multiply to the precedent value
        :type value: float
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises ValueError: If time is not present in the Timeseries
        :return: Timeseries with the value multiply by the precedent value at a specific index
        :rtype: Timeseries
        """
        dt: pendulum.DateTime = build_datetime(time, date_format).in_tz(self.timezone)

        if dt not in self.dataframe["time"]:
            raise ValueError(f"Could not add value at {dt} because timestamp is not in the Timeseries")

        old_value = self.get_value(dt)
        df = self.timeseries.filter(pl.col("time") != dt)
        new_row = pl.DataFrame({"time": [dt], "value": [old_value * value]}).with_columns(
            pl.col("time").cast(pl.Datetime("us", time_zone=self.timezone)),
            pl.col("value").cast(pl.Float64()),
        )
        df = pl.concat([df, new_row])

        return self._return(df, inplace)

    def add_indexes(
        self,
        other: Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict,
        inplace: bool = True,
    ) -> Timeseries:
        """
        Add indexes to the Timeseries based on another timeseries

        :param other: Other timeseries with indexes / values to add to the current Timeseries
        :type other: Timeseries
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises ValueError: If frequency doesn't match or at least one time of the other Timeseries is in the
        current one
        :return: Timeseries with the added indexes
        :rtype: Timeseries
        """
        other = Timeseries(other)
        if len(self.timeseries) == 0:
            other_df = other.dataframe
            return self._return(other_df, inplace)

        other_ts = Timeseries(other)
        if self.frequency != other_ts.frequency:
            raise ValueError("Could not perform add indexes on Timeseries because frequency does not match")
        if other_ts.dataframe["time"].is_in(self.dataframe["time"]).any():
            raise ValueError(
                "Could not add indexes on Timeseries because some indexes to add are not present in Timeseries"
            )

        df = pl.concat([self.timeseries, other_ts.dataframe])

        return self._return(df, inplace)

    def add_index(
        self,
        time: datetime | str,
        value: float,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Timeseries:
        """
        Add index to the Timeseries based on an index and a value

        :param time: Datetime to add
        :type time: datetime or str
        :param value: Value to add
        :type value: float
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :raises ValueError: If the time is in the current Timeseries
        :return: Timeseries with the added index
        :rtype: Timeseries
        """
        dt: pendulum.DateTime = build_datetime(time, date_format).in_tz(self.timezone)

        if len(self.timeseries) == 0:
            raise ValueError("Timeseries should not be empty")

        if dt in self.dataframe["time"]:
            raise ValueError(
                "Could not add indexes on Timeseries because some indexes to add are not present in Timeseries"
            )

        new_row = pl.DataFrame({"time": [dt], "value": [value]}).with_columns(
            pl.col("time").cast(pl.Datetime("us", time_zone=self.timezone)),
            pl.col("value").cast(pl.Float64()),
        )
        df = pl.concat([self.timeseries, new_row])

        return self._return(df, inplace)

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
            )
        elif interpolation_method == "constant":
            df = self.timeseries.upsample(time_column="time", every=frequency).fill_null(
                strategy="forward",
            )
        else:
            raise NotImplementedError("Unsupported interpolation method")

        return self._return(df, inplace)

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

        return self._return(df, inplace)

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

        return self._return(df.dataframe, inplace)

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

        df_to_write = self.timeseries.clone().insert_column(1, pl.lit(attribute).alias("attribute"))

        if concatenate:
            path_obj = Path(path_str)
            if path_obj.exists() and file_format_lower != "pickle":
                try:
                    if file_format_lower == "csv":
                        existing_df = pl.read_csv(path_str, separator=separator, try_parse_dates=True)
                    elif file_format_lower == "parquet":
                        existing_df = pl.read_parquet(path_str)

                    # Concatenate with existing data
                    df_to_write = pl.concat([existing_df, df_to_write])
                except Exception as e:
                    raise ValueError(f"Could not read existing file for concatenation: {e}") from e

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

        return self._return(df, inplace)

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
        lookup = self._get_lookup()
        if dt not in lookup:
            raise KeyError(f"Value for {dt.to_datetime_string()} not found in the Timeseries.")
        return lookup[dt]

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
            template=template,  # type:ignore [arg-type]
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

    def _return(self, df: pl.DataFrame, inplace: bool) -> Timeseries:
        """
        Return the Timeseries object itself or modify existing.

        :return: The Timeseries object
        :rtype: Timeseries
        """
        if inplace:
            old_len = len(self.timeseries)
            self.timeseries = df.sort("time")
            if getattr(self, "frequency", None) is None or len(self.timeseries) != old_len:
                self.frequency = infer_frequency(self.timeseries)
            self._invalidate_cache()
            return self
        return Timeseries(df, self.timezone)

    def get_by_index(self, index: int) -> float:
        n = len(self.timeseries)
        if n == 0 or index >= n or index < -n:
            raise IndexError(f"index {index} is out of bounds for timeseries of length {n}")
        return cast(float, self.timeseries.row(index, named=True)["value"])

    def get_time_by_index(self, index: int) -> pendulum.DateTime:
        n = len(self.timeseries)
        if n == 0 or index >= n or index < -n:
            raise IndexError(f"index {index} is out of bounds for timeseries of length {n}")
        return cast(pendulum.DateTime, pendulum.instance(self.timeseries.row(index, named=True)["time"]))

    def iter_rows(self) -> Generator[tuple[datetime, float], None, None]:
        """
        Iterate over rows of the Timeseries, yielding (time, value) tuples.

        :return: A generator yielding tuples containing (time, value) for each row
        :rtype: Generator[tuple[datetime, float], None, None]
        """
        for row in self.timeseries.iter_rows(named=True):
            yield (row["time"], row["value"])
