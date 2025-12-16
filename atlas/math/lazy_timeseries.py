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
from typing import Literal

import pendulum
import polars as pl

from atlas.io_utils.utils import scan_data_file
from atlas.math.timeseries import Timeseries
from atlas.timing import build_datetime, check_timezone


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

    def set_value(
        self,
        datetime: str | datetime | pendulum.DateTime,
        value: float | None,
        date_format: str = "YYYY-MM-DD HH:mm:ss",
        inplace: bool = True,
    ) -> LazyTimeseries:
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
        :return: LazyTimeseries with the added value
        :rtype: LazyTimeseries
        """
        dt = build_datetime(datetime, date_format).in_tz(self.timezone)
        resampled_ts = self.collect().set_value(dt, value, date_format=date_format, inplace=False)
        lf = resampled_ts.to_lazy()
        return self._return_inplace(lf, inplace)

    def filter(
        self,
        item: list[datetime] | list[pendulum.DateTime] | list[str] | datetime | pendulum.DateTime | str,
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
            item = [build_datetime(i, date_format=date_format).in_tz(self.timezone) for i in item]
            lf = self.timeseries.filter(pl.col("time").is_in(item))
        else:
            date = build_datetime(item, date_format=date_format).in_tz(self.timezone)
            lf = self.timeseries.filter(pl.col("time") == date)

        return self._return_inplace(lf, inplace)

    def slice(
        self,
        start_bound: datetime | pendulum.DateTime | str,
        end_bound: datetime | pendulum.DateTime | str,
        closed: Literal["left", "right", "both", "none"] = "both",
        inplace: bool = True,
    ) -> LazyTimeseries:
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
        lf = self.timeseries.filter(pl.col("time").is_between(date_start, date_end, closed))

        return self._return_inplace(lf, inplace)

    def slice_with_offset(
        self,
        offset: int,
        length: int | None = None,
        inplace: bool = True,
    ) -> LazyTimeseries:
        """Get a slice of the Timeseries

        :param offset: Start index. Negative indexing is supported.
        :param length: Length of the slice. If set to `None`, all rows starting at the offset will be selected.
        :param inplace: Whether to modify the current instance, defaults to True
        :return: The Timeseries object
        """
        lf = self.timeseries.slice(offset, length)
        return self._return_inplace(lf, inplace)

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

        :param frequency: The desired frequency. Can be a string (e.g., '1d', '15m') or a `pendulum.Duration`.
        :type frequency: str or pendulum.Duration
        :param inplace: If True, modifies the object in place. If False, returns a new modified object.
        :type inplace: bool
        :return: The resampled lazy time series, either modified in place or as a new object.
        :rtype: LazyTimeseries
        """
        resampled_ts = self.collect().set_frequency(frequency, inplace=False)
        lf = resampled_ts.to_lazy()
        return self._return_inplace(lf, inplace)

    def abs(self, inplace: bool = True) -> LazyTimeseries:
        """
        Compute the absolute value of each value in the time series.

        :param inplace: If True, modifies the object in place. If False, returns a new modified object.
        :type inplace: bool
        :return: The LazyTimeseries with absolute values, either modified in place or as a new object.
        :rtype: LazyTimeseries
        """
        lf = self.timeseries.with_columns(pl.col("value").abs())
        return self._return_inplace(lf, inplace)

    def first_date(self) -> pendulum.DateTime | None:
        """
        Return the first date in the LazyTimeseries index.

        This operation only collects the first row's timestamp, not the entire dataset.

        :return: The first date in the Timeseries index
        :rtype: pendulum.DateTime or None
        """
        result = self.timeseries.select("time").head(1).collect()
        if result.height > 0:
            return pendulum.instance(result.item())
        return None

    def last_date(self) -> pendulum.DateTime | None:
        """
        Return the last date in the LazyTimeseries index.

        This operation only collects the last row's timestamp, not the entire dataset.

        :return: The last date in the Timeseries index
        :rtype: pendulum.DateTime or None
        """
        result = self.timeseries.select("time").tail(1).collect()
        if result.height > 0:
            return pendulum.instance(result.item())
        return None

    def iter_rows(self) -> Generator[tuple[datetime, float], None, None]:
        """
        Iterate over rows of the LazyTimeseries, yielding (time, value) tuples.

        Note: This method will collect the LazyFrame into memory before iterating.

        :return: A generator yielding tuples containing (time, value) for each row
        :rtype: Generator[tuple[datetime, float], None, None]
        """
        for row in self.timeseries.collect().iter_rows(named=True):
            yield (row["time"], row["value"])

    def _return_inplace(self, lf: pl.LazyFrame, inplace: bool) -> LazyTimeseries:
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

    def round(
        self,
        rounding_precision: int = 0,
        mode: Literal["half_to_even", "half_away_from_zero"] = "half_to_even",
        inplace: bool = True,
    ) -> LazyTimeseries:
        """
        Returns a copy of the timeseries with all the numerical values rounded.

        :param rounding_precision: Number of decimals used to round numerical values.
        :type rounding_precision: int
        :param mode: Rounding strategy.
        :type mode: str
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Rounded LazyTimeseries
        :rtype: LazyTimeseries
        """
        df = self.timeseries.with_columns(pl.col("value").round(rounding_precision, mode))
        return self._return_inplace(df, inplace)
