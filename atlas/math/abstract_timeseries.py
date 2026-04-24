"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

This module provides AbstractTimeseries base class for Timeseries and LazyTimeseries.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generic, Literal, Self, TypeVar

import pandas as pd
import pendulum
import plotly
import plotly.graph_objects
import polars as pl
from pydantic_core import core_schema

from atlas.timing import build_datetime, generate_datetimes, get_duration

TBackend = TypeVar("TBackend", pl.DataFrame, pl.LazyFrame)


class AbstractTimeseries(ABC, Generic[TBackend]):
    """
    Abstract base class for Timeseries implementations.

    Provides shared interface and implementation for both eager (Timeseries)
    and lazy (LazyTimeseries) time series classes.

    """

    timezone: str
    frequency: pendulum.Duration
    timeseries: TBackend

    @abstractmethod
    def _get_data(self) -> TBackend:
        """Return the underlying DataFrame or LazyFrame."""
        ...

    @abstractmethod
    def _return(self, data: TBackend, inplace: bool) -> Self:
        """Wrap data into appropriate type (Timeseries or LazyTimeseries)."""
        ...

    @abstractmethod
    def _get_shape(self) -> tuple[int, int]:
        """Return (rows, columns) of the underlying data."""
        ...

    @classmethod
    @abstractmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        filters: tuple[str, str] | None = None,
        separator: str = ";",
    ) -> Self:
        """
        Load a Timeseries object from a file.

        :param file_path: Path to the file
        :type file_path: str or Path
        :param timezone: Timezone string used to convert datetime values, defaults to "UTC"
        :type timezone: str, optional
        :param filters: Filters columns
        :type filters: tuple[str, str] or None, optional
        :param separator: Export column separator format, defaults to ";"
        :type separator: str, optional
        :raises ValueError: If file format is not supported
        :return: Loaded Timeseries object
        :rtype: Self
        """
        ...

    @classmethod
    def from_values(
        cls,
        start_date: str | datetime | pendulum.DateTime,
        frequency: str | timedelta | pendulum.Duration,
        values: list[float],
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        timezone: str = "UTC",
    ) -> Self:
        """
        Create a Timeseries from start date, frequency and a list of values.

        :param start_date: Start date of the timeseries
        :type start_date: str or datetime or pendulum.DateTime
        :param frequency: Frequency of the timeseries (e.g., "1h", "15m")
        :type frequency: str or pendulum.Duration
        :param values: List of values corresponding to the time intervals
        :type values: list[float]
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param timezone: Timezone string, defaults to "UTC"
        :type timezone: str, optional
        :raises ValueError: If there is no value to insert in the Timeseries
        :return: A Timeseries object with the specified parameters
        :rtype: Self
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

        return cls(df, timezone)  # type: ignore [call-arg]

    @classmethod
    def from_index(
        cls,
        start_date: str | datetime | pendulum.DateTime,
        frequency: str | timedelta | pendulum.Duration,
        end_date: str | datetime | pendulum.DateTime,
        default_value: list[float] | float = 0,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        timezone: str = "UTC",
    ) -> Self:
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
        :rtype: Self
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

        return cls(df, timezone)  # type: ignore [call-arg]

    @classmethod
    @abstractmethod
    def from_timeseries(cls, timeseries: Any, default_value: float | None = None) -> Self:
        """Create a Timeseries from another, using its structure.

        :param timeseries: The input timeseries object
        :param default_value: default value to pass to all timestamp values, defaults to None
        :type default_value: float | None, optional
        :return: The timeseries object instantiated
        :rtype: Self
        """
        ...

    @classmethod
    @abstractmethod
    def from_dataframe(
        cls,
        dataframe: pl.DataFrame | pd.DataFrame,
        timezone: str = "UTC",
    ) -> Self:
        """Create a Timeseries object from a dataframe-like object.

        :param dataframe: The input dataframe
        :type dataframe: pl.DataFrame | pd.DataFrame
        :param timezone: The timezone of the Timeseries, defaults to "UTC"
        :type timezone: str, optional
        :return: The timeseries instantiated from the dataframe-like object
        :rtype: Self
        """
        ...

    @property
    @abstractmethod
    def dataframe(self) -> pl.DataFrame | pl.LazyFrame:
        """Returns the underlying DataFrame or LazyFrame."""
        ...

    @property
    def shape(self) -> tuple[int, int]:
        """Returns the Timeseries shape."""
        return self._get_shape()

    @property
    @abstractmethod
    def index(self) -> list[datetime]:
        """Returns the Timeseries indexes."""
        ...

    @property
    @abstractmethod
    def values(self) -> list[float]:
        """Returns the Timeseries values."""
        ...

    def to_lookup_dict(self) -> dict:
        """Build a {time: value} dict for O(1) lookups. Materializes data on first call."""
        return {t: v for t, v in self.iter_rows()}

    @property
    @abstractmethod
    def timestep(self) -> pendulum.Duration:
        """Return the frequency of the timeseries index."""
        ...

    @property
    @abstractmethod
    def metadata(self) -> dict[str, Any]:
        """Return the metadata of the timeseries."""
        ...

    @abstractmethod
    def __len__(self) -> int:
        """Return the number of rows in the Timeseries."""
        ...

    @abstractmethod
    def __contains__(self, item: datetime | str | pendulum.DateTime) -> bool:
        """Check if a temporal index exists in the Timeseries."""
        ...

    @abstractmethod
    def max(self) -> float:
        """Return the max value in the 'value' column."""
        ...

    @abstractmethod
    def min(self) -> float:
        """Return the min value in the 'value' column."""
        ...

    @abstractmethod
    def sum(self) -> float:
        """Return the sum of the 'value' column."""
        ...

    @abstractmethod
    def first_date(self) -> pendulum.DateTime | None:
        """Return the first date in the Timeseries index."""
        ...

    @abstractmethod
    def last_date(self) -> pendulum.DateTime | None:
        """Return the last date in the Timeseries index."""
        ...

    @abstractmethod
    def get_value(
        self,
        datetime: str | datetime | pendulum.DateTime,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
    ) -> float:
        """Return value at the given datetime."""
        ...

    def filter(
        self,
        item: list[datetime] | list[pendulum.DateTime] | list[str] | datetime | pendulum.DateTime | str,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Self:
        """
        Filter the Timeseries based on a list of datetime.

        :param item: Datetime to filter the Timeseries
        :type item: list[datetime] or datetime or pendulum.DateTime or str
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Filtered Timeseries
        :rtype: Self
        """
        backend = self._get_data()

        if isinstance(item, list):
            item = [build_datetime(i, date_format=date_format).in_tz(self.timezone) for i in item]
            filtered = backend.filter(pl.col("time").is_in(item))
        else:
            date = build_datetime(item, date_format=date_format).in_tz(self.timezone)
            filtered = backend.filter(pl.col("time") == date)

        return self._return(filtered, inplace)

    def slice(
        self,
        start_bound: datetime | pendulum.DateTime | str,
        end_bound: datetime | pendulum.DateTime | str,
        closed: Literal["left", "right", "both", "none"] = "both",
        inplace: bool = True,
    ) -> Self:
        """Get a slice of the Timeseries

        :param start_bound: Datetime to filter the Timeseries
        :param end_bound: Datetime to filter the Timeseries
        :param closed : {'both', 'left', 'right', 'none'}
            Define which sides of the interval are closed (inclusive).
        :param inplace: Whether to modify the current instance, defaults to True
        :return: The Timeseries object
        """
        backend = self._get_data()
        date_start = build_datetime(start_bound).in_tz(self.timezone)
        date_end = build_datetime(end_bound).in_tz(self.timezone)
        sliced = backend.filter(pl.col("time").is_between(date_start, date_end, closed))

        return self._return(sliced, inplace)

    def slice_with_offset(
        self,
        offset: int,
        length: int | None = None,
        inplace: bool = True,
    ) -> Self:
        """Get a slice of the Timeseries

        :param offset: Start index. Negative indexing is supported.
        :param length: Length of the slice. If set to `None`, all rows starting at the offset will be selected.
        :param inplace: Whether to modify the current instance, defaults to True
        :return: The Timeseries object
        """
        backend = self._get_data()
        sliced = backend.slice(offset, length)
        return self._return(sliced, inplace)

    def abs(self, inplace: bool = True) -> Self:
        """Compute the absolute value of each timestamp

        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: The timeseries with absolute values
        :rtype: Self
        """
        backend = self._get_data()
        result = backend.with_columns(pl.col("value").abs())
        return self._return(result, inplace)

    def round(
        self,
        rounding_precision: int = 0,
        mode: Literal["half_to_even", "half_away_from_zero"] = "half_to_even",
        inplace: bool = True,
    ) -> Self:
        """
        Returns a copy of the timeseries with all the numerical values rounded.
        :param rounding_precision: Number of decimals used to round numerical values.
        :type rounding_precision: int
        :param mode: Rounding strategy.
        :type mode: str
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Rounded Timeseries
        :rtype: Self
        """
        backend = self._get_data()
        result = backend.with_columns(pl.col("value").round(rounding_precision, mode))
        return self._return(result, inplace)

    @abstractmethod
    def set_frequency(self, frequency: str | pendulum.Duration, inplace: bool = True) -> Self:
        """
        Change the frequency (timestep) of the time series.

        :param frequency: The desired frequency. Can be a string (e.g., '1d', '15m') or a `pendulum.Duration`.
        :type frequency: str or pendulum.Duration
        :param inplace: If True, modifies the object in place. If False, returns a new modified object.
        :type inplace: bool
        :return: The resampled time series, either modified in place or as a new object.
        :rtype: Self
        """
        ...

    @abstractmethod
    def upsample(
        self,
        frequency: str | pendulum.Duration,
        interpolation_method: Literal["linear", "constant"] = "constant",
        inplace: bool = True,
    ) -> Self:
        """
        Upsample the Timeseries to a higher frequency.

        :param frequency: Frequency string (e.g., "15m", "1h") defining the new time resolution
        :type frequency: str | pendulum.Duration
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :param interpolation_method: Method to fill missing values
        :type interpolation_method: str, optional
        :return: Upsampled Timeseries
        :rtype: Self
        """
        ...

    @abstractmethod
    def groupby(
        self,
        frequency: str | pendulum.Duration,
        agg: Literal["mean", "sum", "min", "max"] = "mean",
        inplace: bool = True,
    ) -> Self:
        """
        Group the Timeseries dynamically by time intervals.

        :param frequency: Grouping interval (e.g., "1h", "1d")
        :type frequency: str or pendulum.Duration
        :param agg: Aggregation method, defaults to "mean"
        :type agg: Literal["mean", "sum", "min", "max"], optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Grouped Timeseries
        :rtype: Self
        """
        ...

    @abstractmethod
    def set_value(
        self,
        time: datetime | str,
        value: float | None,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Self:
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
        :return: Timeseries with the set value
        :rtype: Self
        """
        ...

    @abstractmethod
    def set_values(
        self,
        other: Any,
        inplace: bool = True,
    ) -> Self:
        """
        Set or update values. If the datetime exists, it is overwritten.

        :param other: other timeseries with values to updated self
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Timeseries with the new values
        :rtype: Self
        """
        ...

    @abstractmethod
    def add_index(
        self,
        time: datetime | str,
        value: float,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Self:
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
        :return: Timeseries with the added index
        :rtype: Self
        """
        ...

    @abstractmethod
    def add_indexes(
        self,
        other: Any,
        inplace: bool = True,
    ) -> Self:
        """
        Add indexes to the Timeseries based on another timeseries

        :param other: Other timeseries with indexes / values to add to the current Timeseries
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Timeseries with the added indexes
        :rtype: Self
        """
        ...

    @abstractmethod
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
        """
        ...

    @abstractmethod
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
        """
        ...

    @abstractmethod
    def sum_value_at(
        self,
        time: datetime | str,
        value: float,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Self:
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
        :return: Timeseries with the value added
        :rtype: Self
        """
        ...

    @abstractmethod
    def mul_value_at(
        self,
        time: datetime | str,
        value: float,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> Self:
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
        :return: Timeseries with the value multiplied
        :rtype: Self
        """
        ...

    @abstractmethod
    def interpolate(
        self, interpolation_method: Literal["linear", "constant"] = "constant", inplace: bool = True
    ) -> Self:
        """Interpolate the Timeseries to fill in missing values.

        :param interpolation_method: Interpolation method, defaults to "constant"
        :type interpolation_method: Literal["linear", "constant"], optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Interpolated Timeseries
        :rtype: Self
        """
        ...

    @abstractmethod
    def iter_rows(self) -> Generator[tuple[datetime, float], None, None]:
        """
        Iterate over rows of the Timeseries, yielding (time, value) tuples.

        :return: A generator yielding tuples containing (time, value) for each row
        :rtype: Generator[tuple[datetime, float], None, None]
        """
        ...

    @abstractmethod
    def __repr__(self) -> str:
        """Provide a string representation of the Timeseries object."""
        ...

    @abstractmethod
    def __eq__(self, other: object) -> bool:
        """Implement the equality between two Timeseries."""
        ...

    @abstractmethod
    def __mul__(self, other: Any) -> Self:
        """Multiply all numeric columns by a scalar or another Timeseries."""
        ...

    @abstractmethod
    def __add__(self, other: Any) -> Self:
        """Add all numeric columns by a scalar or timeseries."""
        ...

    @abstractmethod
    def __sub__(self, other: Any) -> Self:
        """Subtract all numeric columns by a scalar or timeseries."""
        ...

    @abstractmethod
    def __truediv__(self, other: Any) -> Self:
        """Divide all numeric columns by a scalar or timeseries."""
        ...

    @abstractmethod
    def __getitem__(self, column_name: str) -> list[float | datetime]:
        """Get column values by name."""
        ...

    @abstractmethod
    def to_frame(self, engine: Literal["polars", "pandas"] = "polars") -> pl.DataFrame | pd.DataFrame | pl.LazyFrame:
        """Return the internal time series as a data frame."""
        ...

    @abstractmethod
    def sort(self, inplace: bool = True) -> Self:
        """Sort the Timeseries by time."""
        ...

    @abstractmethod
    def set_timezone(self, timezone: str) -> None:
        """Convert the datetime column to a new timezone."""
        ...

    @abstractmethod
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
        """Generate a Plotly figure for the Timeseries data."""
        ...

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Get metadata about the timeseries."""
        ...

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.is_instance_schema(
            cls,
            serialization=core_schema.plain_serializer_function_ser_schema(lambda x: "timeseries", when_used="json"),
        )
