"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

This module provides LazyTimeseries.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pendulum
import polars as pl

from atlas.io_utils.utils import get_metadata_from_frame, scan_data_file
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.timeseries import Timeseries
from atlas.timing import build_datetime, check_timezone, infer_frequency


class LazyTimeseries(AbstractTimeseries[pl.LazyFrame]):
    """
    A lazy-evaluated time series class using a Polars LazyFrame backend.

    LazyTimeseries enables efficient, deferred computation on large time series datasets by leveraging
    Polars' lazy execution model. This is particularly useful for workflows where data is too large to fit
    in memory or when chaining multiple transformations before materializing results.
    """

    def __init__(
        self,
        timeseries: pl.LazyFrame | pl.DataFrame | LazyTimeseries | Any | None = None,
        timezone: str = "UTC",
    ) -> None:
        """
        :param timeseries: The input time series data
        :type timeseries: pl.LazyFrame or pl.DataFrame or LazyTimeseries or Timeseries
        :param timezone: Timezone string used to convert datetime values, defaults to "UTC"
        :type timezone: str, optional
        """

        check_timezone(timezone)
        self.timezone: str = timezone

        if isinstance(timeseries, pl.DataFrame):
            timeseries = timeseries.lazy()

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
            schema = timeseries.collect_schema()

            time_columns = [name for name, dtype in schema.items() if dtype.is_temporal()]
            value_columns = [name for name, dtype in schema.items() if dtype.is_numeric()]

            if len(value_columns) != 1:
                raise ValueError("Timeseries must have exactly one numeric column")
            if len(time_columns) != 1:
                raise ValueError("Timeseries must have exactly one datetime column")

            self.timeseries = (
                timeseries.rename({time_columns[0]: "time", value_columns[0]: "value"})
                .with_columns(pl.col("time").cast(pl.Datetime("us", time_zone=timezone)))
                .sort("time")
            )

        else:
            raise ValueError("LazyTimeseries requires a LazyFrame, DataFrame, or another Timeseries object")

    def _get_data(self) -> pl.LazyFrame:
        """Return the underlying LazyFrame."""
        return self.timeseries

    def _get_shape(self) -> tuple[int, int]:
        """Return (rows, columns) of the underlying LazyFrame (requires collection)."""
        collected = self.timeseries.select(pl.len()).collect()
        return (collected.item(), len(self.timeseries.collect_schema()))

    def __repr__(self):
        """String representation of the LazyTimeseries"""
        return f"LazyTimeseries with schema : {self.timeseries.collect_schema()}"

    @property
    def dataframe(self) -> pl.LazyFrame:
        """Returns the underlying LazyFrame."""
        return self.timeseries

    @property
    def lazyframe(self) -> pl.LazyFrame:
        """
        Return the internal Polars LazyFrame.

        :return: The internal lazy time series data
        :rtype: pl.LazyFrame
        """
        return self.timeseries

    @property
    def index(self) -> list[datetime]:
        """Returns the LazyTimeseries indexes.

        Warning: This property materializes the entire time column into memory.
        Use with caution on large datasets. Consider using filter() or slice() operations
        instead to work with subsets of the data lazily.

        :return: List of datetime indexes
        :rtype: list[datetime]
        """
        return self.timeseries.select("time").collect().to_series().to_list()

    @property
    def values(self) -> list[float]:
        """Returns the LazyTimeseries values.

        Warning: This property materializes the entire value column into memory.
        Use with caution on large datasets.

        :return: List of values
        :rtype: list[float]
        """
        return self.timeseries.select("value").collect().to_series().to_list()

    @property
    def timestep(self) -> pendulum.Duration:
        """Return the frequency of the timeseries index.

        Warning: This property requires collecting the data to infer frequency.
        """
        return infer_frequency(self.timeseries.collect())

    @property
    def metadata(self) -> dict:
        """Return the metadata of the timeseries.

        Warning: This property requires collecting the data.
        """
        return self.describe()

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

    @classmethod
    def from_timeseries(cls, timeseries: Any, default_value: float | None = None) -> LazyTimeseries:
        """Create a LazyTimeseries from another timeseries, using its structure.

        :param timeseries: The input timeseries object
        :param default_value: default value to pass to all timestamp values, defaults to None
        :type default_value: float | None, optional
        :return: The LazyTimeseries object instantiated
        :rtype: LazyTimeseries
        """

        # Accept both Timeseries and LazyTimeseries
        if isinstance(timeseries, LazyTimeseries):
            if default_value is not None:
                lf = timeseries.to_frame().with_columns(pl.lit(default_value).alias("value"))
                return cls(lf, timezone=timeseries.timezone)
            else:
                return cls(timeseries)
        elif isinstance(timeseries, Timeseries):
            if default_value is not None:
                lf = timeseries.to_lazy().with_columns(pl.lit(default_value).alias("value"))
                return cls(lf, timezone=timeseries.timezone)
            else:
                return cls(timeseries.to_lazy(), timezone=timeseries.timezone)
        else:
            raise TypeError("Input has to be a timeseries object, if using a dataframe, use 'from_dataframe' ")

    @classmethod
    def from_dataframe(
        cls,
        dataframe: pl.DataFrame | pd.DataFrame | pl.LazyFrame,
        timezone: str = "UTC",
    ) -> LazyTimeseries:
        """Create a LazyTimeseries object from a dataframe-like object.

        :param dataframe: The input dataframe
        :type dataframe: pl.DataFrame | pd.DataFrame | pl.LazyFrame
        :param timezone: The timezone of the LazyTimeseries, defaults to "UTC"
        :type timezone: str, optional
        :return: The LazyTimeseries instantiated from the dataframe-like object
        :rtype: LazyTimeseries
        """
        if isinstance(dataframe, pl.LazyFrame | pl.DataFrame):
            return cls(dataframe, timezone)
        elif isinstance(dataframe, pd.DataFrame):
            return cls(pl.from_pandas(dataframe), timezone)
        else:
            raise TypeError("Input has to be a dataframe-like object.")

    def to_frame(
        self,
        engine: str = "polars",
    ) -> pl.LazyFrame:
        """
        Return the internal Polars LazyFrame.

        :param engine: Engine to use (only 'polars' supported for LazyTimeseries)
        :type engine: str
        :return: The internal lazy time series data
        :rtype: pl.LazyFrame
        """
        if engine != "polars":
            raise ValueError("LazyTimeseries only supports engine='polars'")
        return self.timeseries

    def to_lazy(self) -> pl.LazyFrame:
        """
        Return the internal LazyFrame.

        :return: The internal lazy time series data
        :rtype: pl.LazyFrame
        """
        return self.timeseries

    def collect(self):
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
    ) -> float:
        """Return values at the given datetime. Raises KeyError if exact match is not found.

        This operation only collects the matching row, not the entire dataset.

        :param datetime: Datetime to get value for
        :type datetime: str or datetime
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :return: The value at the timestamp requested
        :rtype: float
        :raises ValueError: If the timeseries is empty
        :raises KeyError: If the datetime is not found in the timeseries
        """

        if len(self) == 0:
            raise ValueError("Can't get value on empty timeseries.")

        dt = build_datetime(datetime, date_format).in_tz(self.timezone)

        result = self.timeseries.filter(pl.col("time") == dt).select("value").collect()

        if result.height > 0:
            return result.item()
        else:
            raise KeyError(f"Value for {dt.to_datetime_string()} not found in the Timeseries.")

    def max(self) -> float:
        """Return the max value column.

        This operation only collects the aggregated max value, not the entire dataset.

        :return: The Timeseries max value
        :rtype: float or None
        """
        result = self.timeseries.select(pl.col("value").max()).collect().item()
        if result is None:
            raise RuntimeError("Timeseries is empty, can't get the maximum value")
        return result

    def min(self) -> float:
        """Return the min value column.

        This operation only collects the aggregated min value, not the entire dataset.

        :return: The Timeseries min value
        :rtype: float
        """
        result = self.timeseries.select(pl.col("value").min()).collect().item()
        if result is None:
            raise RuntimeError("Timeseries is empty, can't get the minimum value")
        return result

    def sum(self) -> float:
        """Return the sum of the 'value' column.

        This operation only collects the aggregated sum value, not the entire dataset.
        Returns 0.0 for empty timeseries.

        :return: The Timeseries sum value
        :rtype: float
        """
        return self.timeseries.select(pl.col("value").sum()).collect().item()

    def __len__(self) -> int:
        """Return the number of rows in the LazyTimeseries.

        This operation only collects the count, not the entire dataset.

        :return: The number of rows
        :rtype: int
        """
        return self.timeseries.select(pl.len()).collect().item()

    def __contains__(self, item: datetime | str | pendulum.DateTime) -> bool:
        """Check if a temporal index exists in the LazyTimeseries.

        This operation only collects the count of matching rows, not the entire dataset.

        :param item: Datetime to check for existence
        :type item: datetime or str or pendulum.DateTime
        :return: True if the datetime exists in the LazyTimeseries index, False otherwise
        :rtype: bool
        """
        try:
            dt = build_datetime(item).in_tz(self.timezone)
            count = self.timeseries.filter(pl.col("time") == dt).select(pl.len()).collect().item()
            return count > 0
        except Exception:
            return False

    def set_frequency(self, frequency: str | pendulum.Duration, inplace: bool = True) -> LazyTimeseries:
        """
        Change the frequency (timestep) of the lazy time series.

        ⚠️ WARNING: This method materializes all data into memory.

        :param frequency: The desired frequency. Can be a string (e.g., '1d', '15m') or a `pendulum.Duration`.
        :type frequency: str or pendulum.Duration
        :param inplace: If True, modifies the object in place. If False, returns a new modified object.
        :type inplace: bool
        :return: The resampled lazy time series, either modified in place or as a new object.
        :rtype: LazyTimeseries
        """
        resampled_ts = self.collect().set_frequency(frequency, inplace=False)
        lf = resampled_ts.to_lazy()
        return self._return(lf, inplace)

    def _row_at(self, index: int) -> dict:
        if index >= 0:
            result = self.timeseries.slice(index, 1).collect()
            if result.height == 0:
                raise IndexError(f"index {index} is out of bounds")
        else:
            tail_n = -index
            result = self.timeseries.tail(tail_n).collect()
            if result.height < tail_n:
                raise IndexError(f"index {index} is out of bounds for timeseries of length {result.height}")
            result = result.head(1)
        return result.row(0, named=True)

    def get_by_index(self, index: int) -> float:
        return cast(float, self._row_at(index)["value"])

    def get_time_by_index(self, index: int) -> pendulum.DateTime:
        return pendulum.instance(self._row_at(index)["time"])

    def iter_rows(self) -> Generator[tuple[datetime, float]]:
        """
        Iterate over rows of the LazyTimeseries, yielding (time, value) tuples.

        Note: This method will collect the LazyFrame into memory before iterating.

        :return: A generator yielding tuples containing (time, value) for each row
        :rtype: Generator[tuple[datetime, float], None, None]
        """
        for row in self.timeseries.collect().iter_rows(named=True):
            yield (row["time"], row["value"])

    def _return(self, lf: pl.LazyFrame, inplace: bool) -> LazyTimeseries:
        """
        Return the LazyTimeseries object itself or create a new one.

        Helper method to handle the inplace parameter pattern consistently across methods.

        :param lf: The LazyFrame to use
        :type lf: pl.LazyFrame
        :param inplace: If True, modifies the object in place. If False, returns a new object.
        :type inplace: bool
        :return: The LazyTimeseries object, either modified in place or as a new object.
        :rtype: LazyTimeseries
        """
        if inplace:
            self.timeseries = lf.sort("time")
            return self
        return LazyTimeseries(lf.sort("time"), timezone=self.timezone)

    def upsample(
        self,
        frequency: str | pendulum.Duration,
        interpolation_method: str = "constant",
        inplace: bool = True,
    ) -> LazyTimeseries:
        """
        Upsample the LazyTimeseries to a higher frequency.

        ⚠️ WARNING: This method materializes all data into memory.

        :param frequency: Frequency string (e.g., "15m", "1h")
        :type frequency: str | pendulum.Duration
        :param interpolation_method: Method to fill missing values
        :type interpolation_method: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Upsampled LazyTimeseries
        :rtype: LazyTimeseries
        """
        upsampled_ts = self.collect().upsample(frequency, interpolation_method, inplace=False)
        lf = upsampled_ts.to_lazy()
        return self._return(lf, inplace)

    def groupby(
        self,
        frequency: str | pendulum.Duration,
        agg: str = "mean",
        inplace: bool = True,
    ) -> LazyTimeseries:
        """
        Group the LazyTimeseries dynamically by time intervals.

        ⚠️ WARNING: This method materializes all data into memory.

        :param frequency: Grouping interval (e.g., "1h", "1d")
        :type frequency: str or pendulum.Duration
        :param agg: Aggregation method, defaults to "mean"
        :type agg: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Grouped LazyTimeseries
        :rtype: LazyTimeseries
        """
        grouped_ts = self.collect().groupby(frequency, agg, inplace=False)
        lf = grouped_ts.to_lazy()
        return self._return(lf, inplace)

    def set_value(
        self,
        time: datetime | str,
        value: float | None,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> LazyTimeseries:
        """
        Update a value at a specific datetime.

        ⚠️ WARNING: This method materializes all data into memory.

        :param time: Datetime to set
        :type time: datetime or str
        :param value: Value to set
        :type value: float or int
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: LazyTimeseries with the set value
        :rtype: LazyTimeseries
        """
        updated_ts = self.collect().set_value(time, value, date_format, inplace=False)
        lf = updated_ts.to_lazy()
        return self._return(lf, inplace)

    def set_values(
        self,
        other: LazyTimeseries | Timeseries | pl.DataFrame | pl.LazyFrame,
        inplace: bool = True,
    ) -> LazyTimeseries:
        """
        Set or update values. If the datetime exists, it is overwritten.

        ⚠️ WARNING: This method materializes all data into memory.

        :param other: other timeseries with values to updated self
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: LazyTimeseries with the new values
        :rtype: LazyTimeseries
        """
        if isinstance(other, LazyTimeseries):
            other = other.collect()
        updated_ts = self.collect().set_values(other, inplace=False)
        lf = updated_ts.to_lazy()
        return self._return(lf, inplace)

    def add_index(
        self,
        time: datetime | str,
        value: float,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> LazyTimeseries:
        """
        Add index to the LazyTimeseries based on an index and a value.

        ⚠️ WARNING: This method materializes all data into memory.

        :param time: Datetime to add
        :type time: datetime or str
        :param value: Value to add
        :type value: float
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: LazyTimeseries with the added index
        :rtype: LazyTimeseries
        """
        updated_ts = self.collect().add_index(time, value, date_format, inplace=False)
        lf = updated_ts.to_lazy()
        return self._return(lf, inplace)

    def add_indexes(
        self,
        other: LazyTimeseries | Timeseries | pl.DataFrame | pl.LazyFrame,
        inplace: bool = True,
    ) -> LazyTimeseries:
        """
        Add indexes to the LazyTimeseries based on another timeseries.

        Indexes from ``other`` already present in the current LazyTimeseries are ignored; only
        the missing ones are added.

        ⚠️ WARNING: This method materializes all data into memory.

        :param other: Other timeseries with indexes / values to add
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: LazyTimeseries with the added indexes
        :rtype: LazyTimeseries
        """
        if isinstance(other, LazyTimeseries):
            other = other.collect()
        updated_ts = self.collect().add_indexes(other, inplace=False)
        lf = updated_ts.to_lazy()
        return self._return(lf, inplace)

    def sum_value_at(
        self,
        time: datetime | str,
        value: float,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> LazyTimeseries:
        """
        Add to an existing value at a specific datetime.

        ⚠️ WARNING: This method materializes all data into memory.

        :param time: Datetime to add to the value
        :type time: datetime or str
        :param value: Value to add to the precedent value
        :type value: float
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: LazyTimeseries with the value added
        :rtype: LazyTimeseries
        """
        updated_ts = self.collect().sum_value_at(time, value, date_format, inplace=False)
        lf = updated_ts.to_lazy()
        return self._return(lf, inplace)

    def mul_value_at(
        self,
        time: datetime | str,
        value: float,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> LazyTimeseries:
        """
        Multiply to an existing value at a specific datetime.

        ⚠️ WARNING: This method materializes all data into memory.

        :param time: Datetime to multiply by the value
        :type time: datetime or str
        :param value: Value to multiply to the precedent value
        :type value: float
        :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
        :type date_format: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: LazyTimeseries with the value multiplied
        :rtype: LazyTimeseries
        """
        updated_ts = self.collect().mul_value_at(time, value, date_format, inplace=False)
        lf = updated_ts.to_lazy()
        return self._return(lf, inplace)

    def interpolate(self, interpolation_method: str = "constant", inplace: bool = True) -> LazyTimeseries:
        """
        Interpolate the LazyTimeseries to fill in missing values.

        ⚠️ WARNING: This method materializes all data into memory.

        :param interpolation_method: Interpolation method, defaults to "constant"
        :type interpolation_method: str, optional
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Interpolated LazyTimeseries
        :rtype: LazyTimeseries
        """
        interpolated_ts = self.collect().interpolate(interpolation_method, inplace=False)
        lf = interpolated_ts.to_lazy()
        return self._return(lf, inplace)

    def to_file(
        self,
        path: str | Path,
        file_format: str = "csv",
        separator: str = ";",
    ) -> None:
        """
        Export the LazyTimeseries to a file.

        ⚠️ WARNING: This method materializes all data into memory.

        :param path: Destination file path
        :type path: str
        :param file_format: Export file format, defaults to "csv"
        :type file_format: str, optional
        :param separator: Export column separator format, defaults to ";"
        :type separator: str, optional
        """
        self.collect().to_file(path, file_format, separator)

    def to_file_with_attribute(
        self,
        path: str | Path,
        attribute: str,
        file_format: str = "csv",
        separator: str = ";",
        concatenate: bool = True,
    ) -> None:
        """
        Export the LazyTimeseries to a file with an attribute column.

        ⚠️ WARNING: This method materializes all data into memory.

        :param path: Destination file path
        :type path: str or Path
        :param attribute: Attribute name to add as a column
        :type attribute: str
        :param file_format: Export file format, defaults to "csv"
        :type file_format: str, optional
        :param separator: Export column separator format, defaults to ";"
        :type separator: str, optional
        :param concatenate: If True, concatenate with existing file data, defaults to True
        :type concatenate: bool, optional
        """
        self.collect().to_file_with_attribute(path, attribute, file_format, separator, concatenate)

    def __eq__(self, other: object) -> bool:
        """
        Implement the equality between two LazyTimeseries.

        ⚠️ WARNING: This method materializes all data into memory.

        :param other: The LazyTimeseries to compare with
        :type other: LazyTimeseries
        :return: True if equal, False otherwise
        :rtype: bool
        """
        if isinstance(other, LazyTimeseries):
            return self.timeseries.collect().equals(other.timeseries.collect())
        raise TypeError("Comparison with non-LazyTimeseries objects is not supported")

    def __mul__(self, other: float | LazyTimeseries | Timeseries) -> LazyTimeseries:
        """
        Multiply all numeric columns by a scalar or another timeseries.

        ⚠️ WARNING: Operations with other timeseries materialize data into memory.

        :param other: Other timeseries or scalar
        :type other: float | LazyTimeseries | Timeseries
        :return: Multiplied LazyTimeseries
        :rtype: LazyTimeseries
        """
        if isinstance(other, int | float):
            lf = self.timeseries.with_columns(pl.col("value").mul(other))
            return LazyTimeseries(lf, self.timezone)
        else:
            # For timeseries operations, collect and compute
            if isinstance(other, LazyTimeseries):
                other = other.collect()
            result = self.collect() * other
            return LazyTimeseries(result.to_lazy(), self.timezone)

    def __add__(self, other: float | LazyTimeseries | Timeseries) -> LazyTimeseries:
        """
        Add all numeric columns by a scalar or timeseries.

        ⚠️ WARNING: Operations with other timeseries materialize data into memory.

        :param other: Other timeseries or scalar
        :type other: float | LazyTimeseries | Timeseries
        :return: Added LazyTimeseries
        :rtype: LazyTimeseries
        """
        if isinstance(other, int | float):
            lf = self.timeseries.with_columns(pl.col("value").add(other))
            return LazyTimeseries(lf, self.timezone)
        else:
            if isinstance(other, LazyTimeseries):
                other = other.collect()
            result = self.collect() + other
            return LazyTimeseries(result.to_lazy(), self.timezone)

    def __sub__(self, other: float | LazyTimeseries | Timeseries) -> LazyTimeseries:
        """
        Subtract all numeric columns by a scalar or timeseries.

        ⚠️ WARNING: Operations with other timeseries materialize data into memory.

        :param other: Other timeseries or scalar
        :type other: float | LazyTimeseries | Timeseries
        :return: Subtracted LazyTimeseries
        :rtype: LazyTimeseries
        """
        if isinstance(other, int | float):
            lf = self.timeseries.with_columns(pl.col("value").sub(other))
            return LazyTimeseries(lf, self.timezone)
        else:
            if isinstance(other, LazyTimeseries):
                other = other.collect()
            result = self.collect() - other
            return LazyTimeseries(result.to_lazy(), self.timezone)

    def __truediv__(self, other: float | LazyTimeseries | Timeseries) -> LazyTimeseries:
        """
        Divide all numeric columns by a scalar or timeseries.

        ⚠️ WARNING: Operations with other timeseries materialize data into memory.

        :param other: Other timeseries or scalar
        :type other: float | LazyTimeseries | Timeseries
        :return: Divided LazyTimeseries
        :rtype: LazyTimeseries
        """
        if isinstance(other, int | float):
            if other == 0:
                raise ZeroDivisionError("Division by zero is not allowed")
            lf = self.timeseries.with_columns(pl.col("value").truediv(other))
            return LazyTimeseries(lf, self.timezone)
        else:
            if isinstance(other, LazyTimeseries):
                other = other.collect()
            result = self.collect() / other
            return LazyTimeseries(result.to_lazy(), self.timezone)

    def __getitem__(self, column_name: str) -> list[float | datetime]:
        """
        Get column values by name.

        ⚠️ WARNING: This method materializes the column into memory.

        :param column_name: Column name ('time' or 'value')
        :type column_name: str
        :return: List of column values
        :rtype: list[float | datetime]
        """
        if column_name not in ("time", "value"):
            raise KeyError("Column name has to be either time or value")
        return self.timeseries.select(column_name).collect().to_series().to_list()

    def sort(self, inplace: bool = True) -> LazyTimeseries:
        """
        Sort the LazyTimeseries by time.

        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Sorted LazyTimeseries
        :rtype: LazyTimeseries
        """
        return self._return(self.timeseries, inplace)

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

    def plot(
        self,
        title: str = "Time Series Plot",
        height: int = 500,
        width: int = 800,
        show_grid: bool = True,
        line_color: str = "#1f77b4",
        line_shape: str = "hv",
        template: str = "plotly_white",
    ):
        """
        Generate a Plotly figure for the LazyTimeseries data.

        ⚠️ WARNING: This method materializes all data into memory.

        :param title: Plot title
        :param height: Plot height in pixels
        :param width: Plot width in pixels
        :param show_grid: Whether to show grid lines
        :param line_color: Color of the line plot
        :param line_shape: Shape of the plot
        :param template: Plotly template to use
        :return: Plotly figure object
        """
        return self.collect().plot(title, height, width, show_grid, line_color, line_shape, template)

    def describe(self) -> dict:
        """
        Get metadata about the timeseries.

        ⚠️ WARNING: This method materializes all data into memory.

        :return: A dictionary containing timeseries metadata
        :rtype: dict
        """
        return get_metadata_from_frame(self.timeseries.collect())
