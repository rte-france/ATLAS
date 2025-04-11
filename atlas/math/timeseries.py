from __future__ import annotations

import pickle
from datetime import timedelta
from typing import Literal, Self

import polars as pl


class Timeseries:
    """A time series wrapper class using Polars backend.

    :param timeseries: The input time series data.
    :type timeseries: pl.DataFrame or Timeseries
    :param timezone: Timezone string used to convert datetime values, defaults to "UTC"
    :type timezone: str, optional
    :raises ValueError: If the timeseries cannot be parsed or validated as a proper Polars DataFrame
    """

    def __init__(
        self,
        timeseries: pl.DataFrame | Timeseries,
        timezone: str = "UTC",
    ) -> None:
        self.timezone = timezone
        self.timeseries: pl.DataFrame | None = None

        if isinstance(timeseries, Timeseries):
            self.timeseries = timeseries.get_timeseries()
            self.timezone = timeseries.timezone
        else:
            try:
                df = pl.DataFrame(timeseries)
            except Exception as e:
                raise ValueError("Timeseries cannot be formatted as a DataFrame") from e

            time_column = df.select(pl.selectors.datetime() | pl.selectors.date()).columns
            if len(time_column) != 1:
                raise ValueError("Timeseries must have exactly one datetime column")
            df = df.rename({time_column: "time"}).with_columns(
                pl.col("time").dt.convert_time_zone(self.timezone),
            )

            self.timeseries = df

    def remove_na(self, inplace: bool = True) -> Timeseries:
        """Remove rows containing null values.

        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: The cleaned time series
        :rtype: Timeseries
        """
        dt = self.timeseries.drop_nulls()
        if inplace:
            self.timeseries = dt
            return self
        return Timeseries(dt)

    def get_timeseries(self) -> pl.DataFrame:
        """Return the internal Polars DataFrame.

        :return: The internal time series data
        :rtype: pl.DataFrame
        """
        return self.timeseries

    def set_timezone(self, timezone: str) -> None:
        """Convert the datetime column to a new timezone.

        :param timezone: Timezone string
        :type timezone: str
        """
        self.timezone = timezone
        self.timeseries = self.timeseries.with_columns(
            pl.col("time").dt.convert_time_zone(self.timezone),
        )

    def sort(
        self,
        variables: str | list[str],
        inplace: bool = True,
        descending: bool | list[bool] = False,
    ) -> Timeseries:
        """Sort the time series by the given variable(s).

        :param variables: Variable(s) to sort by
        :type variables: str or list[str]
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :param descending: Sort in descending order, defaults to False
        :type descending: bool or list[bool], optional
        :return: Sorted time series
        :rtype: Timeseries
        """
        df = self.timeseries.sort(variables)
        if inplace:
            self.timeseries = df
            return self
        return Timeseries(df)

    def groupby(
        self,
        granularity: str | timedelta,
        agg: str = Literal["mean", "sum", "min", "max"],
        inplace: bool = True,
    ) -> Timeseries:
        """Group the time series dynamically by time intervals.

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
        df = self.timeseries.group_by_dynamic("time", every=granularity)
        if agg == "mean":
            df.agg(
                pl.selectors.numeric().mean(),
            )
        elif agg == "sum":
            df.agg(
                pl.selectors.numeric().sum(),
            )
        elif agg == "min":
            df.agg(
                pl.selectors.numeric().min(),
            )
        elif agg == "max":
            df.agg(
                pl.selectors.numeric().max(),
            )
        else:
            raise ValueError("Unsupported aggregation function")

        if inplace:
            self.timeseries = df
            return self
        return Timeseries(df)

    def select(self, variables: list[str], inplace: bool = True) -> Timeseries:
        """Select the specified variables from the time series.

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
        return Timeseries(df)

    def remove_duplicated(
        self,
        variables: str | list[str],
        inplace: bool = True,
    ) -> Timeseries:
        """Remove duplicated rows based on given variable(s).

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
        return Timeseries(df)

    def merge(
        self,
        other: Self | pl.DataFrame,
        by: str = "time",
        how: Literal["inner", "left", "right", "full", "semi", "anti", "cross", "outer"] = "inner",
        suffixes: str | None = None,
        inplace: bool = True,
    ) -> Timeseries:
        """Merge this time series with another.

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
        return Timeseries(df)

    def drop(self, variables: list[str], inplace: bool = True) -> Timeseries:
        """Remove specified variables from the time series.

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
        return Timeseries(df)

    def get_granularity(self, unit: Literal["hour", "minute", "second"] = "hour") -> float:
        """Compute the time interval (granularity) between data points.

        :param unit: Time unit to return the granularity in, defaults to "hour"
        :type unit: Literal["hour", "minute", "second"], optional
        :raises ValueError: If fewer than two time points exist or if unit is unsupported
        :return: Time interval in the specified unit
        :rtype: float
        """
        times = self.timeseries["time"].to_list()
        if len(times) < 2:
            raise ValueError("Not enough time points to calculate granularity")
        delta = (times[1] - times[0]).total_seconds()

        if unit == "hour":
            return delta / 3600
        if unit == "minute":
            return delta / 60
        if unit == "second":
            return delta
        raise ValueError("Unsupported unit")

    def rename(self, old_cols: list[str], new_cols: list[str], inplace: bool = True) -> Timeseries:
        """Rename columns in the time series.

        :param old_cols: List of current column names
        :type old_cols: list[str]
        :param new_cols: List of new column names
        :type new_cols: list[str]
        :param inplace: Whether to modify the current instance, defaults to True
        :type inplace: bool, optional
        :return: Modified time series or None
        :rtype: Timeseries or None
        """
        renamed = self.timeseries.rename(dict(zip(old_cols, new_cols, strict=False)))
        if inplace:
            self.timeseries = renamed
            return self
        return Timeseries(renamed)

    def export(
        self,
        path: str,
        file_format: Literal["csv", "parquet", "pickle"] = "csv",
    ) -> None:
        """Export the time series to a file.

        :param path: Destination file path
        :type path: str
        :param file_format: Export file format, defaults to "csv"
        :type file_format: Literal["csv", "parquet", "pickle"], optional
        :raises ValueError: If file extension doesn't match format
        :raises NotImplementedError: If the file format is not supported
        """
        file_format = file_format.lower()

        if not path.lower().endswith(file_format):
            raise ValueError("Format and file extension don't match.")

        if file_format == "csv":
            self.timeseries.write_csv(path)
        elif file_format == "parquet":
            self.timeseries.write_parquet(path)
        elif file_format == "pickle":
            with open(path, "wb") as f:
                pickle.dump(self, f)
        else:
            raise NotImplementedError("Format not supported")
