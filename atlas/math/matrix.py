"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Matrix
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl
import pytz

from atlas.math.timeseries import Timeseries


class Matrix:
    """Base class for storing Timeseries objects indexed by scenario keys or datetimes."""

    def __init__(self, matrix: pd.DataFrame | pl.DataFrame, timezone: str = "UTC") -> None:
        """
        Initialize the matrix.

        :param matrix: DataFrame containing the matrix data.
        :type matrix: pd.DataFrame | pl.DataFrame
        :param timezone: Timezone for the datetime column.
        :type timezone: str
        """
        self._check_timezone(timezone)
        self.timezone = timezone

        df: pl.DataFrame = pl.DataFrame(matrix) if isinstance(matrix, pd.DataFrame) else matrix

        time_column = df.select(pl.selectors.datetime() | pl.selectors.date()).columns

        self.matrix: pl.DataFrame = (
            df.rename({time_column[0]: "time"})
            .with_columns(pl.col("time").cast(pl.Datetime("us", time_zone=timezone)))
            .sort("time")
        )
        self.indexes: list[str] = self._get_indexes()

        if len(time_column) + len(self.indexes) != len(df.columns):
            raise ValueError(
                f"Matrix must have exactly one time column and the other columns has to be numerical,"
                f"but found {len(df.columns)} columns in total."
            )

    @classmethod
    def from_file(cls, file_path: str | Path) -> Matrix:
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
            matrix = pl.read_csv(file_path)
        elif file_path.suffix == ".parquet":
            matrix = pl.read_parquet(file_path)
        return cls(matrix)

    def _get_indexes(self) -> list[str]:
        """
        Get the indexes of the matrix.

        :return: List of indexes.
        :rtype: list[str]
        """
        time_columns = self.matrix.select(pl.selectors.datetime() | pl.selectors.date()).columns
        if len(time_columns) != 1:
            raise ValueError("Matrix must have exactly one time column")
        time_column = time_columns[0]
        return self.matrix.drop(time_column).columns

    @staticmethod
    def _check_timezone(timezone: str) -> None:
        """
        Check if the timezone is valid.

        :raises ValueError: If the timezone is not valid
        """
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

        self.matrix = self.matrix.drop(index)
        self.indexes = self._get_indexes()

    def get_matrix(self) -> pl.DataFrame:
        """
        Get the matrix data.

        :return: The matrix data.
        :rtype: pl.DataFrame
        """
        return self.matrix

    def to_file(self, file_path: str | Path, file_format: str = "parquet") -> None:
        """
        Save the matrix to a file in either CSV or Parquet format.

        :param file_path: Output file path.
        :type file_path: str | Path
        :param format: Output format: "csv" or "parquet".
        :type format: str
        """
        file_path = Path(file_path)
        if file_format == "csv":
            self.matrix.write_csv(file_path)
        elif file_format == "parquet":
            self.matrix.write_parquet(file_path)
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'csv' or 'parquet'.")
