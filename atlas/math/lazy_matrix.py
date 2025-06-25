"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements LazyMatrix
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from atlas.io_utils.utils import scan_data_file
from atlas.math.matrix import Matrix
from atlas.timing import check_timezone


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
            schema = matrix.collect_schema().to_frame()
            time_column = schema.select(pl.selectors.datetime() | pl.selectors.date()).columns
            value_column = schema.select(pl.selectors.numeric()).columns

            if len(time_column) != 1:
                raise ValueError("LazyMatrix must have exactly one datetime column")

            if len(time_column) + len(value_column) != len(schema.columns):
                raise ValueError("LazyMatrix must have N columns one for datetime and N-1 for numerical values")

            self.matrix = (
                matrix.rename({time_column[0]: "time"})
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
        schema = self.matrix.collect_schema().to_frame()
        time_columns = schema.select(pl.selectors.datetime() | pl.selectors.date()).columns

        time_column = time_columns[0]
        return [col for col in self.matrix.collect_schema() if col != time_column]
