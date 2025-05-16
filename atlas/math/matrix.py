"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Matrix
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import pendulum
import plotly.graph_objects as go
import polars as pl
import pytz

from atlas.math.timeseries import Timeseries


class Matrix:
    """A container for time-indexed `Timeseries` data, supporting both eager and lazy operations.

    This class abstracts over Polars and Pandas DataFrames to provide a uniform way
    to manage multiple time series, each associated with a unique index or scenario key."""

    def __init__(self, matrix: pd.DataFrame | pl.DataFrame | Matrix, timezone: str = "UTC") -> None:
        """
        :param matrix: DataFrame containing the matrix data.
        :type matrix: pd.DataFrame | pl.DataFrame | Matrix
        :param timezone: Timezone for the datetime column.
        :type timezone: str
        """
        self._check_timezone(timezone)
        self._check_matrix(matrix)

        self._set_matrix(matrix=matrix, timezone=timezone)
        self.indexes: list[str] = self.get_indexes()

    def __repr__(self):
        """Provide a string representation of the Matrix object."""
        return f"Matrix : {self.matrix}"

    @classmethod
    def describe(cls, matrix: pd.DataFrame | pl.DataFrame | Matrix) -> dict[str, Any]:
        """
        Get metadata about the matrix.

        :param matrix: DataFrame containing the matrix data.
        :type matrix: pd.DataFrame | pl.DataFrame | Matrix
        :return: A dictionnary containing matrix metadata
        :rtype: dict[str, Any]
        """
        if isinstance(matrix, pd.DataFrame):
            df = pl.DataFrame(matrix)
        elif isinstance(matrix, Matrix):
            df = matrix.get_matrix()
        elif isinstance(matrix, pl.DataFrame):
            df = matrix
        else:
            raise NotImplementedError("Can't parse input data. Provide a dataframe or a Matrix")

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
        else:
            raise ValueError("Expected one string column exactly")

        summary["numeric_columns"] = numeric_cols

        return summary

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        filters: tuple[str, str] | None = None,
        separator: str = ";",
    ) -> Matrix:
        """
        Load a Matrix from a file.

        :param file_path: Path to the file (CSV or Parquet).
        :type file_path: str | Path
        :return: A Matrix object.
        :rtype: Matrix
        """
        if isinstance(file_path, str):
            file_path = Path(file_path)
        if file_path.suffix == ".csv":
            matrix = pl.read_csv(file_path, separator=separator, try_parse_dates=True)
        elif file_path.suffix == ".parquet":
            matrix = pl.read_parquet(file_path)
        if filters:
            matrix = matrix.filter(pl.col(f"{filters[0]}") == filters[1]).drop(filters[0])
        return cls(matrix, timezone)

    def _set_matrix(self, matrix: pl.DataFrame | pd.DataFrame | Matrix, timezone: str) -> None:
        """Set matrix attribute"""
        if isinstance(matrix, Matrix):
            self.matrix: pl.DataFrame = matrix.matrix
            self.timezone: str = matrix.timezone
        else:
            df: pl.DataFrame = pl.DataFrame(matrix) if isinstance(matrix, pd.DataFrame) else matrix

            time_column = df.select(pl.selectors.datetime() | pl.selectors.date()).columns

            self.matrix: pl.DataFrame = (  # type: ignore[no-redef]
                df.rename({time_column[0]: "time"})
                .with_columns(pl.col("time").cast(pl.Datetime("us", time_zone=timezone)))
                .sort("time")
            )
            self.timezone: str = timezone  # type: ignore[no-redef]

    @staticmethod
    def _check_matrix(matrix: pl.DataFrame | pd.DataFrame | Matrix) -> None:
        """Check matrix data structure"""
        if isinstance(matrix, Matrix):
            return
        df: pl.DataFrame = pl.DataFrame(matrix) if isinstance(matrix, pd.DataFrame) else matrix

        time_columns = df.select(pl.selectors.datetime() | pl.selectors.date()).columns
        if len(time_columns) != 1:
            raise ValueError("Matrix must have exactly one time column")

        value_columns = df.select(pl.selectors.numeric()).columns

        if len(time_columns) + len(value_columns) != len(df.columns):
            raise ValueError("Matrix must have N columns one for datetime and N-1 for numerical values")

    def get_indexes(self) -> list[str]:
        """
        Get the indexes of the matrix.

        :return: List of indexes.
        :rtype: list[str]
        """
        return self.matrix.select(pl.selectors.numeric()).columns

    @staticmethod
    def _check_timezone(timezone: str) -> None:
        """Check if the timezone is valid."""
        if timezone not in pytz.all_timezones:
            raise ValueError(f"Invalid timezone: {timezone}")

    def __len__(self) -> int:
        """
        Number of timeseries in the matrix.

        :return: Number of elements in the matrix.
        :rtype: int
        """
        return len(self.indexes)

    def __contains__(self, index: str) -> bool:
        """
        Check if an index exists in the matrix.

        :param index: The index to check.
        :type index: Index
        :return: True if index exists, False otherwise.
        :rtype: bool
        """
        return index in self.indexes

    def __getitem__(self, index: str) -> pl.DataFrame:
        """
        Get a timeseries by index.

        :param index: Index key.
        :type index: Index
        :raises KeyError: If the index is not found.
        :return: The Timeseries object.
        :rtype: Timeseries
        """
        if index not in self.indexes:
            raise KeyError(f"No timeseries found for index: {index}")
        return self.matrix.select("time", index)

    def __eq__(self, other: object) -> bool:
        """
        Check equality with another matrix.

        :param other: Another matrix instance.
        :type other: object
        :raises TypeError: If the object to compare is not a Matrix
        :return: True if equal, False otherwise.
        :rtype: bool
        """
        if not isinstance(other, Matrix):
            raise TypeError("Cannot compare with non-Matrix object")

        return self.matrix.equals(other.matrix)

    def to_lazy(self) -> pl.LazyFrame:
        """
        Convert the internal Polars DataFrame to a LazyFrame.

        :return: A Polars LazyFrame representation of the time series
        :rtype: pl.LazyFrame
        """
        return self.matrix.lazy()

    def add(
        self,
        timeseries: Timeseries | pl.DataFrame | pd.DataFrame | dict[str, list],
        index: str,
    ) -> None:
        """
        Add a timeseries to the matrix.

        :param index: Index to add into the matrix
        :type index: str
        :param timeseries: Timeseries to add.
        :type timeseries: Timeseries
        :raises TypeError: If types are invalid.
        """
        if index in self.indexes:
            raise KeyError(f"Index {index} already exists in the matrix.")
        timeseries = Timeseries(timeseries) if not isinstance(timeseries, Timeseries) else timeseries

        self.matrix = self.matrix.join(
            timeseries.get_data(engine="polars").rename({"value": index}),  # type: ignore[arg-type]
            on="time",
            how="full",
            coalesce=True,
        )
        self.indexes = self.get_indexes()

    def delete(self, index: str) -> None:
        """
        Delete a timeseries by index.

        :param index: Index key to delete from the matrix
        :type index: str
        :raises KeyError: If index is not found.
        """
        if index not in self.indexes:
            raise KeyError(f"No timeseries to delete at index: {index}")

        self.matrix = self.matrix.drop(index)
        self.indexes = self.get_indexes()

    def get_matrix(self) -> pl.DataFrame:
        """
        Get the matrix data.

        :return: The matrix data.
        :rtype: pl.DataFrame
        """
        return self.matrix

    def to_file(
        self,
        path: str | Path,
        file_format: Literal["csv", "parquet", "pickle"] = "csv",
        separator: str = ";",
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
            self.matrix.write_csv(path, separator=separator)
        elif file_format_lower == "parquet":
            self.matrix.write_parquet(path)
        elif file_format_lower == "pickle":
            with open(path, "wb") as f:
                pickle.dump(self, f)
        else:
            raise NotImplementedError("Format not supported")

    def plot(
        self,
        title: str = "Matrix Timeseries Plot",
        height: int = 500,
        width: int = 800,
        show_grid: bool = True,
        line_shape: Literal["hv", "linear", "spline"] = "hv",
        template: str = "plotly_white",
    ) -> go.Figure:
        """
        Generate an interactive Plotly figure for the Matrix data with a slider to select indexes.

        :param title: Plot title
        :param height: Plot height in pixels
        :param width: Plot width in pixels
        :param show_grid: Whether to show grid lines
        :param line_shape: Shape of the plot lines
        :param template: Plotly template to use
        :return: Plotly figure object
        """
        df = self.get_matrix()
        index_columns = self.indexes
        time_col = "time"

        fig = go.Figure()

        for i, idx in enumerate(index_columns):
            visible = i == 0  # Only show first index initially
            fig.add_trace(
                go.Scatter(
                    x=df[time_col],
                    y=df[idx],
                    mode="lines",
                    name=idx,
                    line_shape=line_shape,
                    visible=visible,
                )
            )

        steps = []
        for i, idx in enumerate(index_columns):
            step = {
                "method": "update",
                "label": idx,
                "args": [
                    {"visible": [j == i for j in range(len(index_columns))]},
                    {"title": f"{title} - {idx}"},
                ],
            }
            steps.append(step)

        sliders = [
            {
                "active": 0,
                "currentvalue": {"prefix": "Index: "},
                "pad": {"t": 50},
                "steps": steps,
            }
        ]

        fig.update_layout(
            sliders=sliders,
            title=title,
            height=height,
            width=width,
            template=template,
            xaxis={
                "title": "Time",
                "showgrid": show_grid,
                "gridcolor": "lightgray" if show_grid else None,
            },
            yaxis={
                "title": "Value",
                "showgrid": show_grid,
                "gridcolor": "lightgray" if show_grid else None,
            },
        )

        return fig
