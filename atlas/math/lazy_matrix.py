"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements LazyMatrix
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl

from atlas.io_utils.utils import scan_data_file
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.matrix import Matrix
from atlas.math.timeseries import Timeseries
from atlas.timing import check_timezone
from atlas.typing import TimeseriesDict


class LazyMatrix:
    """Base class for lazily storing Timeseries-like data indexed by scenario keys or datetimes."""

    def __init__(self, matrix: pl.LazyFrame | LazyMatrix | Matrix, timezone: str = "UTC") -> None:
        """
        Initialize the LazyMatrix.

        :param matrix: LazyFrame, Matrix, or LazyMatrix object.
        :type matrix: pl.LazyFrame | LazyMatrix | Matrix
        :param timezone: Timezone for the datetime column.
        :type timezone: str
        """
        check_timezone(timezone)
        self.timezone = timezone

        if isinstance(matrix, LazyMatrix):
            self.matrix = matrix.get_matrix()
            self.timezone = matrix.timezone
        elif isinstance(matrix, Matrix):
            self.matrix = matrix.to_lazy()
            self.timezone = matrix.timezone
        elif isinstance(matrix, pl.LazyFrame):
            schema = matrix.collect_schema()

            time_columns = [name for name, dtype in schema.items() if dtype.is_temporal()]
            value_columns = [name for name, dtype in schema.items() if dtype.is_numeric()]

            if len(time_columns) != 1:
                raise ValueError("LazyMatrix must have exactly one datetime column")

            if len(time_columns) + len(value_columns) != len(schema):
                raise ValueError("LazyMatrix must have N columns one for datetime and N-1 for numerical values")

            self.matrix = (
                matrix.rename({time_columns[0]: "time"})
                .with_columns(pl.col("time").cast(pl.Datetime("us", time_zone=self.timezone)))
                .sort("time")
            )
        else:
            raise TypeError("LazyMatrix requires a LazyFrame, Matrix, or LazyMatrix")

        self.indexes = self._get_indexes()

    @property
    def lazyframe(self) -> pl.LazyFrame:
        """Returns the Matrix DataFrame"""
        return self.matrix

    @property
    def index(self) -> list[str]:
        """Returns the Matrix indexes (e.g columns names)"""
        return self._get_indexes()

    def __repr__(self):
        """String representation of the Matrix"""
        return f"LazyMatrix with schema : {self.matrix.collect_schema()}"

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        filters: tuple[str, str] | None = None,
        separator: str = ";",
    ) -> LazyMatrix:
        """
        Load a LazyMatrix from a file.

        :param file_path: Path to the file
        :param separator: CSV separator (if applicable)
        :param timezone: Timezone to apply
        :return: LazyMatrix instance
        """

        return cls(scan_data_file(file_path, filters, separator), timezone)

    def get_matrix(self) -> pl.LazyFrame:
        """Return internal lazy frame."""
        return self.matrix

    def collect(self) -> Matrix:
        """Collect the lazy frame and return a regular Matrix object."""
        return Matrix(self.matrix.collect(), timezone=self.timezone)

    def _get_indexes(self) -> list[str]:
        """Identify index columns by excluding the time column."""
        schema = self.matrix.collect_schema()

        time_columns = [name for name, dtype in schema.items() if dtype.is_temporal()]
        time_column = time_columns[0] if time_columns else "time"

        return [col for col in schema.names() if col != time_column]

    def add(
        self,
        timeseries: LazyTimeseries | pl.LazyFrame | Timeseries | pl.DataFrame | pd.DataFrame | TimeseriesDict,
        index: str,
    ) -> None:
        """
        Add a timeseries to the lazy matrix.

        :param timeseries: Timeseries to add.
        :type timeseries: Timeseries | pl.DataFrame | pd.DataFrame | dict[str, list]
        :param index: Index to add into the matrix
        :type index: str
        :raises KeyError: If index already exists in the matrix.
        """
        if index in self.indexes:
            raise KeyError(f"Index {index} already exists in the matrix.")

        if isinstance(timeseries, LazyTimeseries):
            lazy_ts = timeseries.lazyframe
        elif isinstance(timeseries, pl.LazyFrame):
            lazy_ts = timeseries
        else:
            lazy_ts = Timeseries(timeseries).to_frame(engine="polars").rename({"value": index}).lazy()  # type: ignore [operator]

        # Join with the existing matrix
        self.matrix = self.matrix.join(
            lazy_ts,
            on="time",
            how="full",
            coalesce=True,
        )

        # Update indexes
        self.indexes = self._get_indexes()

    def delete(self, index: str) -> None:
        """
        Delete a timeseries by index from the lazy matrix.

        :param index: Index key to delete from the matrix
        :type index: str
        :raises KeyError: If index is not found.
        """
        if index not in self.indexes:
            raise KeyError(f"No timeseries to delete at index: {index}")

        self.matrix = self.matrix.drop(index)

        self.indexes = self._get_indexes()

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

    def select(self, index: str) -> LazyTimeseries:
        """
        Get a lazy timeseries by index.

        This operation does not materialize the data, keeping it lazy.

        :param index: Index key.
        :type index: str
        :raises KeyError: If the index is not found.
        :return: The LazyTimeseries object.
        :rtype: LazyTimeseries
        """
        if index not in self.indexes:
            raise KeyError(f"Index {index} not found in the matrix.")

        # Select time and the specified column, rename to 'value'
        lazy_ts = self.matrix.select(["time", index]).rename({index: "value"})
        return LazyTimeseries(lazy_ts, timezone=self.timezone)
