"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ScenarioMatrix
"""

from __future__ import annotations

import pickle
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal, Self

import pandas as pd
import pendulum
import plotly.graph_objects as go
import polars as pl

from atlas.io_utils.utils import get_metadata_from_frame, read_data_file
from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.timing import check_timezone, get_duration, infer_frequency
from atlas.type import TimeseriesDict


class ScenarioMatrix(AbstractScenarioMatrix[pl.DataFrame]):
    """A container for time-indexed `Timeseries` data, supporting both eager and lazy operations.

    This class abstracts over Polars and Pandas DataFrames to provide a uniform way
    to manage multiple time series, each associated with a unique index or scenario key."""

    def __init__(
        self, matrix: pd.DataFrame | pl.DataFrame | ScenarioMatrix | None = None, timezone: str = "UTC"
    ) -> None:
        """
        :param matrix: DataFrame containing the matrix data.
        :type matrix: pd.DataFrame | pl.DataFrame | ScenarioMatrix
        :param timezone: Timezone for the datetime column.
        :type timezone: str
        """
        check_timezone(timezone)
        self._check_matrix(matrix)

        self._set_matrix(matrix=matrix, timezone=timezone)
        self.indexes: list[str] = self._get_indexes()

    def __repr__(self):
        """Provide a string representation of the ScenarioMatrix object."""
        return f"ScenarioMatrix : {self.matrix}"

    def describe(self) -> dict[str, Any]:
        """
        Get metadata about the ScenarioMatrix.

        :return: A dictionnary containing matrix metadata
        :rtype: dict[str, Any]
        """
        return get_metadata_from_frame(self.matrix)

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        filters: tuple[str, str] | None = None,
        separator: str = ";",
    ) -> ScenarioMatrix:
        """
        Load a ScenarioMatrix from a file.

        :param file_path: Path to the file (CSV or Parquet).
        :type file_path: str | Path
        :return: A ScenarioMatrix object.
        :rtype: ScenarioMatrix
        """

        return cls(read_data_file(file_path, filters, separator), timezone)

    def _set_matrix(self, matrix: pl.DataFrame | pd.DataFrame | ScenarioMatrix | None, timezone: str) -> None:
        """Set matrix attribute"""
        if matrix is None:
            self.matrix: pl.DataFrame = pl.DataFrame(
                schema={
                    "time": pl.Datetime("us", time_zone=timezone),
                }
            )
            self.timezone: str = timezone
            return
        if isinstance(matrix, ScenarioMatrix):
            self.matrix: pl.DataFrame = matrix.matrix  # type: ignore[no-redef]
            self.timezone: str = matrix.timezone  # type: ignore[no-redef]
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
    def _check_matrix(matrix: pl.DataFrame | pd.DataFrame | ScenarioMatrix | None) -> None:
        """Check matrix data structure"""
        if matrix is None:
            return
        if isinstance(matrix, ScenarioMatrix):
            return
        df: pl.DataFrame = pl.DataFrame(matrix) if isinstance(matrix, pd.DataFrame) else matrix

        time_columns = df.select(pl.selectors.datetime() | pl.selectors.date()).columns
        if len(time_columns) != 1:
            raise ValueError("ScenarioMatrix must have exactly one time column")

        value_columns = df.select(pl.selectors.numeric()).columns

        if len(value_columns) < 1:
            raise ValueError("ScenarioMatrix must have at least one numeric column")

        if len(time_columns) + len(value_columns) != len(df.columns):
            raise ValueError("ScenarioMatrix must have N columns one for datetime and N-1 for numerical values")

    def _get_data(self) -> pl.DataFrame:
        """Return the underlying DataFrame."""
        return self.matrix

    def _return(self, data: pl.DataFrame, inplace: bool) -> ScenarioMatrix:
        """Wrap data into ScenarioMatrix type."""
        if inplace:
            self.matrix = data
            return self
        return self.__class__(data, timezone=self.timezone)

    def _get_indexes(self) -> list[str]:
        """
        Get the indexes of the matrix.

        :return: List of indexes.
        :rtype: list[str]
        """
        return self.matrix.select(pl.selectors.numeric()).columns

    def _trim_null_extremities(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Remove rows at the beginning and end where all value columns are null.
        This is called after delete and select operations to clean up the matrix edges.
        """
        if len(df) == 0:
            return df

        # Get value columns (all except time)
        value_columns = [col for col in df.columns if col != "time"]

        if len(value_columns) == 0:
            return df

        # Create boolean mask: True where all value columns are null
        all_null_mask = df.select(pl.all_horizontal([pl.col(idx).is_null() for idx in value_columns])).to_series()

        # Find indices where at least one value column is not null
        valid_indices = (~all_null_mask).arg_true()

        if len(valid_indices) == 0:
            # All rows are null, keep only time column with no data
            return df

        # Get first and last valid indices
        first_valid_idx = valid_indices[0]
        last_valid_idx = valid_indices[-1]

        # Trim the matrix
        return df.slice(first_valid_idx, last_valid_idx - first_valid_idx + 1)

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

    def __getitem__(self, index: str) -> Timeseries:
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
        df = self._trim_null_extremities(self.matrix.select(["time", index]))
        return Timeseries(df)

    def select(self, index: str) -> Timeseries:
        """
        Get a timeseries by index.

        :param index: Index key.
        :type index: Index
        :raises KeyError: If the index is not found.
        :return: The Timeseries object.
        :rtype: Timeseries
        """
        return self.__getitem__(index)

    def __eq__(self, other: object) -> bool:
        """
        Check equality with another matrix.

        :param other: Another matrix instance.
        :type other: object
        :raises TypeError: If the object to compare is not a ScenarioMatrix
        :return: True if equal, False otherwise.
        :rtype: bool
        """
        if not isinstance(other, ScenarioMatrix):
            raise TypeError("Cannot compare with non-ScenarioMatrix object")

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
        timeseries: AbstractTimeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict,
        index: str,
    ) -> None:
        """
        Add a timeseries to the matrix.

        :param index: Index to add into the matrix
        :type index: str
        :param timeseries: Timeseries to add.
        :type timeseries: Timeseries
        """
        if index in self.indexes:
            raise KeyError(f"Index {index} already exists in the matrix.")

        df = timeseries.collect() if isinstance(timeseries, LazyTimeseries) else timeseries
        timeseries = Timeseries(df) if not isinstance(timeseries, Timeseries) else timeseries

        self.matrix = self.matrix.join(
            timeseries.to_frame(engine="polars").rename({"value": index}),  # type: ignore[arg-type]
            on="time",
            how="full",
            coalesce=True,
        ).sort("time")

        self.indexes = self._get_indexes()

    def delete(self, index: str) -> None:
        """
        Delete a timeseries by index.

        :param index: Index key to delete from the matrix
        :type index: str
        :raises KeyError: If index is not found.
        """
        if index not in self.indexes:
            raise KeyError(f"No timeseries to delete at index: {index}")

        self.matrix = self.matrix.drop(index).sort("time")
        self.indexes = self._get_indexes()

        self.matrix = self._trim_null_extremities(self.matrix)

    def replace(
        self,
        index: str,
        timeseries: Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict,
    ) -> None:
        """
        Replace a Timeseries in the matrix and keep indexes sorted.

        :param timeseries: Timeseries data to add.
        :type timeseries: Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict
        :param index: Datetime key for the new forecast.
        :type index: str | datetime
        """
        self.delete(index=index)
        self.add(timeseries=timeseries, index=index)

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

    def to_file_with_attribute(
        self,
        path: str | Path,
        attribute: str,
        file_format: Literal["csv", "parquet", "pickle"] = "csv",
        separator: str = ";",
        concatenate: bool = True,
    ) -> None:
        """
        Export the ScenarioMatrix to a file with an attribute column.

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

        df_to_write = self.matrix.clone().insert_column(1, pl.lit(attribute).alias("attribute"))

        if concatenate:
            path_obj = Path(path_str)
            if path_obj.exists() and file_format_lower != "pickle":
                try:
                    if file_format_lower == "csv":
                        existing_df = pl.read_csv(path_str, separator=separator, try_parse_dates=True)
                    elif file_format_lower == "parquet":
                        existing_df = pl.read_parquet(path_str)

                    df_to_write = pl.concat([existing_df, df_to_write])
                except Exception:
                    pass

        if file_format_lower == "csv":
            df_to_write.write_csv(path_str, separator=separator)
        elif file_format_lower == "parquet":
            df_to_write.write_parquet(path_str)
        elif file_format_lower == "pickle":
            with open(path_str, "wb") as f:
                pickle.dump(self, f)
        else:
            raise NotImplementedError("Format not supported")

    @property
    def dataframe(self) -> pl.DataFrame:
        """Returns the ScenarioMatrix DataFrame"""
        return self.matrix

    @property
    def shape(self) -> tuple[int, int]:
        """Returns the ScenarioMatrix shape"""
        return self._get_shape()

    @property
    def index(self) -> list[str]:
        """Returns the ScenarioMatrix indexes (e.g columns names)"""
        return self._get_indexes()

    @property
    def metadata(self) -> dict[str, Any]:
        """Return the metadata of the timeseries."""
        return self.describe()

    def _get_shape(self) -> tuple[int, int]:
        """Return (rows, columns) of the underlying Polars DataFrame."""
        return self.matrix.shape

    def plot(
        self,
        title: str = "ScenarioMatrix Timeseries Plot",
        height: int = 500,
        width: int = 800,
        show_grid: bool = True,
        line_shape: Literal["hv", "linear", "spline"] = "hv",
        template: str = "plotly_white",
    ) -> go.Figure:
        """
        Generate an interactive Plotly figure for the ScenarioMatrix data with a slider to select indexes.

        :param title: Plot title
        :param height: Plot height in pixels
        :param width: Plot width in pixels
        :param show_grid: Whether to show grid lines
        :param line_shape: Shape of the plot lines
        :param template: Plotly template to use
        :return: Plotly figure object
        """
        df = self.get_matrix()
        index_columns = self._get_indexes()
        time_col = "time"

        fig = go.Figure()

        for i, idx in enumerate(index_columns):
            visible = i == 0
            fig.add_trace(
                go.Scatter(
                    x=df[time_col],  # type: ignore[arg-type]
                    y=df[idx],  # type: ignore[arg-type]
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

    def _upsample(
        self, frequency: str | pendulum.Duration, interpolation_method: Literal["linear", "constant"] = "constant"
    ) -> pl.DataFrame:
        """
        Upsample all scenarios to a higher frequency.

        :param frequency: Target frequency for upsampling
        :type frequency: str | pendulum.Duration
        :param interpolation_method: Method to fill missing values
        :type interpolation_method: Literal["linear", "constant"]
        :return: Upsampled DataFrame
        :rtype: pl.DataFrame
        """
        if interpolation_method == "linear":
            df = (
                self.matrix.upsample(time_column="time", every=frequency)
                .with_columns([pl.col(col).interpolate_by("time") for col in self.indexes])
                .fill_null(strategy="forward")
                .sort("time")
            )
        elif interpolation_method == "constant":
            df = self.matrix.upsample(time_column="time", every=frequency).fill_null(strategy="forward").sort("time")
        else:
            raise NotImplementedError("Unsupported interpolation method")

        return df

    def _downsample(
        self, frequency: str | pendulum.Duration, agg: Literal["mean", "sum", "min", "max"] = "mean"
    ) -> pl.DataFrame:
        """
        Downsample all scenarios by grouping time intervals.

        :param frequency: Target frequency for downsampling
        :type frequency: str | pendulum.Duration
        :param agg: Aggregation method
        :type agg: Literal["mean", "sum", "min", "max"]
        :return: Downsampled DataFrame
        :rtype: pl.DataFrame
        """
        grouped_df = self.matrix.group_by_dynamic("time", every=frequency)

        if agg == "mean":
            df = grouped_df.agg([pl.col(col).mean() for col in self.indexes])
        elif agg == "sum":
            df = grouped_df.agg([pl.col(col).sum() for col in self.indexes])
        elif agg == "min":
            df = grouped_df.agg([pl.col(col).min() for col in self.indexes])
        elif agg == "max":
            df = grouped_df.agg([pl.col(col).max() for col in self.indexes])
        else:
            raise NotImplementedError("Unsupported aggregation function")

        return df.sort("time")

    def set_frequency(self, frequency: str | timedelta | pendulum.Duration, inplace: bool = True) -> Self:
        """
        Change the frequency (timestep) of all scenario time series in the matrix.

        This method upscales or downscales all scenarios to the specified frequency,
        similar to the `set_frequency` method for individual timeseries.

        :param frequency: The desired frequency. Can be a string (e.g., '1d', '15m') or a `pendulum.Duration`.
        :type frequency: str or pendulum.Duration
        :param inplace: If True, modifies the object in place. If False, returns a new modified object.
        :type inplace: bool
        :return: The resampled scenario matrix, either modified in place or as a new object.
        :rtype: ScenarioMatrix
        """
        if len(self.matrix) == 0:
            return self if inplace else self.__class__(self.matrix.clone(), self.timezone)

        new_timestep = get_duration(frequency)
        current_frequency = infer_frequency(self.matrix)

        if new_timestep > current_frequency:
            df = self._downsample(new_timestep)
        elif new_timestep < current_frequency:
            df = self._upsample(new_timestep)
        else:
            df = self.matrix.clone() if not inplace else self.matrix

        if inplace:
            self.matrix = df
            return self
        else:
            return self.__class__(df, self.timezone)
