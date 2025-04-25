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
from typing import TYPE_CHECKING, Literal, cast

import pendulum
import plotly
import plotly.graph_objects
import polars as pl
import pytz

import atlas.config as cfg

if TYPE_CHECKING:
    import pandas as pd

import plotly.express as px


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
        timeseries: pl.DataFrame | Timeseries | pd.DataFrame | dict[str, list] | None = None,
        timezone: str = "UTC",
    ) -> None:
        self._check_timezone(timezone)

        self.timezone: str = timezone
        self.timeseries: pl.DataFrame = pl.DataFrame()
        if timeseries is None:
            self.timeseries = pl.DataFrame(
                schema={"time": pl.Datetime("us", time_zone=self.timezone), "value": pl.Float64()}
            )
        elif isinstance(timeseries, Timeseries):
            self.timeseries = timeseries.get_data()
            self.timezone = timeseries.timezone
        else:
            try:
                df = timeseries if isinstance(timeseries, pl.DataFrame) else pl.DataFrame(timeseries)
            except Exception as e:
                raise ValueError("Timeseries cannot be formatted as a DataFrame") from e

            time_column = df.select(pl.selectors.datetime() | pl.selectors.date()).columns
            value_column = df.select(pl.selectors.numeric()).columns
            if len(value_column) != 1:
                raise ValueError("Timeseries must have exactly one numeric column")
            if len(time_column) != 1:
                raise ValueError("Timeseries must have exactly one datetime column")
            df = df.rename({time_column[0]: "time", value_column[0]: "value"}).with_columns(
                pl.col("time").cast(pl.Datetime("us", time_zone=timezone))
            )

            self.timeseries = df
            self.sort()

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

    def __mul__(self, other: float | Timeseries) -> Timeseries:
        """Multiply all numeric columns by a scalar or another Timeseries."""
        if isinstance(other, (int, float)):
            df = self.timeseries.with_columns(pl.selectors.numeric().mul(other))
        elif isinstance(other, Timeseries):
            df = (
                self._join(
                    other=other,
                    how="full",
                )
                .fill_null(1)
                .with_columns(pl.col("value").mul(pl.col("value_right")).alias("value"))
                .select("time", "value")
            )

        return Timeseries(df, self.timezone)

    def __add__(self, other: float | Timeseries) -> Timeseries:
        """Add all numeric columns by a scalar or timeseries."""
        if isinstance(other, (int, float)):
            df = self.timeseries.with_columns(pl.selectors.numeric().add(other))
        elif isinstance(other, Timeseries):
            df = (
                self._join(
                    other=other,
                    how="full",
                )
                .fill_null(0)
                .with_columns(pl.col("value").add(pl.col("value_right")).alias("value"))
                .select("time", "value")
            )

        return Timeseries(df, self.timezone)

    def __sub__(self, other: float | Timeseries) -> Timeseries:
        """Subtract all numeric columns by a scalar or timeseries."""
        if isinstance(other, (int, float)):
            df = self.timeseries.with_columns(pl.selectors.numeric().sub(other))
        elif isinstance(other, Timeseries):
            df = (
                self._join(
                    other=other,
                    how="full",
                )
                .fill_null(0)
                .with_columns(pl.col("value").sub(pl.col("value_right")).alias("value"))
                .select("time", "value")
            )

        return Timeseries(df, self.timezone)

    def __truediv__(self, other: float | Timeseries) -> Timeseries:
        """Divide all numeric columns by a scalar or timeseries."""
        if isinstance(other, (int, float)):
            if other == 0:
                raise ZeroDivisionError("Division by zero is not allowed")
            df = self.timeseries.with_columns(pl.selectors.numeric().truediv(other))
        elif isinstance(other, Timeseries):
            df = (
                self._join(
                    other=other,
                    how="full",
                )
                .fill_null(1)
                .with_columns(pl.col("value").truediv(pl.col("value_right")).alias("value"))
                .select("time", "value")
            )

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
        df = self.timeseries.sort("time", descending=descending)
        if inplace:
            self.timeseries = df
            return self
        return Timeseries(df, self.timezone)

    def set_value(self, time: datetime | str, value: float | None, inplace: bool = True) -> Timeseries:
        """
        Set or update a value at a specific datetime. If the datetime exists, it is overwritten.

        :param time: Datetime to set
        :type time: datetime or str
        :param value: Value to set
        :type value: float or int
        """
        dt: pendulum.DateTime = self._check_date(time)
        dt.in_tz(self.timezone)

        if len(self.timeseries) == 0:
            df = pl.DataFrame({"time": [dt], "value": [value]}).with_columns(
                pl.col("time").dt.replace_time_zone(self.timezone)
            )
            if inplace:
                self.timeseries = df
                return self

            return Timeseries(df, self.timezone)

        df = self.timeseries.filter(pl.col("time") != dt)
        new_row = pl.DataFrame({"time": [dt], "value": [value]}).with_columns(
            pl.col("time").cast(pl.Datetime("us", time_zone=self.timezone))
        )
        df = pl.concat([df, new_row]).sort("time")

        if inplace:
            self.timeseries = df
            return self

        return Timeseries(df, self.timezone)

    @classmethod
    def generate_datetimes(
        cls,
        start: str | datetime,
        end: str | datetime,
        freq: str,
        timezone: str = "UTC",
    ) -> list[pendulum.DateTime]:
        """
        Generate a list of datetimes using pendulum.

        :param start: Start datetime
        :param end: End datetime
        :param freq: Frequency (e.g. "1h", "15m", "1d")
        :param timezone: Timezone string, defaults to "UTC"
        :return: List of datetime objects
        """
        start_date: pendulum.DateTime = cls._check_date(start)
        end_date: pendulum.DateTime = cls._check_date(end)

        start_date = start_date.in_tz(timezone)
        end_date = end_date.in_tz(timezone)

        step = pendulum.duration(**Timeseries._parse_freq(freq))
        return [start_date + i * step for i in range(int((end_date - start_date) / step) + 1)]

    @staticmethod
    def _check_date(time: str | datetime | pendulum.DateTime) -> pendulum.DateTime:
        """Check if the date is valid."""
        try:
            dt: pendulum.DateTime = (
                pendulum.from_format(time, fmt=cfg.DATE_FORMAT) if isinstance(time, str) else pendulum.instance(time)
            )
            if not isinstance(dt, pendulum.DateTime):
                raise TypeError("Time input must be a valid datetime object or string")
            return dt  # noqa: TRY300
        except Exception as e:
            raise ValueError(f"Invalid date format: {time}") from e

    @staticmethod
    def _parse_freq(freq: str) -> dict:
        """Parse a freq string like '15m' or '1h' into pendulum duration kwargs."""
        if freq.endswith("m"):
            return {"minutes": int(freq[:-1])}
        if freq.endswith("h"):
            return {"hours": int(freq[:-1])}
        if freq.endswith("d"):
            return {"days": int(freq[:-1])}
        raise ValueError(f"Unsupported frequency: {freq}")

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

    def _join(
        self,
        other: Timeseries | pl.DataFrame,
        by: str = "time",
        how: Literal["inner", "left", "right", "full", "semi", "anti", "cross", "outer"] = "inner",
        suffixes: str = "_right",
    ) -> pl.DataFrame:
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
        return self.timeseries.join(other, on=by, how=how, suffix=suffixes, coalesce=True)

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
            item = [pendulum.instance(i).in_tz(self.timezone) if isinstance(i, datetime) else i for i in item]
            df = self.timeseries.filter(pl.col("time").is_in(item))
        elif isinstance(item, str):
            date = pendulum.from_format(item, fmt=cfg.DATE_FORMAT, tz=self.timezone)
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

    def max(self) -> float | None:
        """Return the max value in the 'value' column."""
        if "value" in self.timeseries.columns and len(self.timeseries) > 0:
            return cast("float", self.timeseries["value"].max())
        return None

    def min(self) -> float | None:
        """Return the min value in the 'value' column."""
        if "value" in self.timeseries.columns and len(self.timeseries) > 0:
            return cast("float", self.timeseries["value"].min())
        return None

    def interpolate(self, method: Literal["linear", "constant"] = "constant", inplace: bool = False) -> Timeseries:
        """Interpolate the time series to fill in missing values.
        :param method: Interpolation method, defaults to "constant"
        :type method: str, optional
        :param inplace: Whether to modify the current instance, defaults to False
        :type inplace: bool, optional
        :raises NotImplementedError: If the method is not supported
        :return: Interpolated time series
        :rtype: Timeseries
        """
        if method == "linear":
            df = self.timeseries.interpolate()
        elif method == "constant":
            df = self.timeseries.fill_null(strategy="forward")
        else:
            raise NotImplementedError("Unsupported interpolation method, use 'linear' or 'constant'")
        if inplace:
            self.timeseries = df
            return self

        return Timeseries(df, self.timezone)

    def get_value(self, datetime: str | datetime | pendulum.DateTime) -> dict:
        """Return values at the given datetime. If exact match is not found, interpolate."""
        df = self.filter(datetime, inplace=False).get_data()
        if len(df) > 0:
            return df.to_dicts()[0]["value"]

        df = (
            self.set_value(datetime, None, inplace=False)
            .interpolate(inplace=False)
            .filter(datetime, inplace=False)
            .get_data()
        )
        if len(df) > 0:
            return df.to_dicts()[0]["value"]
        return {"time": datetime, "value": None}

    def plot(  # noqa: PLR0913
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
        Generate a Plotly figure for the time series data.

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
        :param template: Plotly template to use, defaults to "plotly_white"
        :type template: str, optional
        :param variable: Column to plot (if None, uses 'value' column), defaults to None
        :type variable: str, optional
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
