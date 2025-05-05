"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements LazyMatrix
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytz

from atlas.math.matrix import Matrix


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
        self._check_timezone(timezone)
        self.timezone = timezone

        if isinstance(matrix, LazyMatrix):
            self.matrix = matrix.get_data()
            self.timezone = matrix.timezone
        elif isinstance(matrix, Matrix):
            self.matrix = matrix.to_lazy()
            self.timezone = matrix.timezone
        elif isinstance(matrix, pl.LazyFrame):
            schema = matrix.collect_schema().to_frame()
            time_column = schema.select(pl.selectors.datetime() | pl.selectors.date()).columns

            if len(time_column) != 1:
                raise ValueError("LazyMatrix must have exactly one datetime column")

            self.matrix = (
                matrix.rename({time_column[0]: "time"})
                .with_columns(pl.col("time").cast(pl.Datetime("us", time_zone=self.timezone)))
                .sort("time")
            )
        else:
            raise TypeError("LazyMatrix requires a LazyFrame, Matrix, or LazyMatrix")

        self.indexes = self._get_indexes()

    @classmethod
    def from_file(cls, file_path: str | Path, separator: str = ";", timezone: str = "UTC") -> LazyMatrix:
        """
        Load a LazyMatrix from a file.

        :param file_path: Path to the file
        :param separator: CSV separator (if applicable)
        :param timezone: Timezone to apply
        :return: LazyMatrix instance
        """
        file_path = Path(file_path)
        if file_path.suffix == ".csv":
            matrix = pl.scan_csv(file_path, separator=separator)
        elif file_path.suffix == ".parquet":
            matrix = pl.scan_parquet(file_path)
        else:
            raise ValueError("Unsupported file format. Only CSV and Parquet are supported.")
        return cls(matrix, timezone=timezone)

    def get_data(self) -> pl.LazyFrame:
        """Return internal lazy frame."""
        return self.matrix

    def collect(self) -> Matrix:
        """Collect the lazy frame and return a regular Matrix object."""
        return Matrix(self.matrix.collect(), timezone=self.timezone)

    def _get_indexes(self) -> list[str]:
        """Identify index columns by excluding the time column."""
        schema = self.matrix.collect_schema().to_frame()
        time_columns = schema.select(pl.selectors.datetime() | pl.selectors.date()).columns

        if len(time_columns) != 1:
            raise ValueError("LazyMatrix must have exactly one datetime column")

        time_column = time_columns[0]
        return [col for col in self.matrix.schema if col != time_column]

    @staticmethod
    def _check_timezone(timezone: str) -> None:
        """Validate timezone string."""
        if timezone not in pytz.all_timezones:
            raise ValueError(f"Invalid timezone: {timezone}")
