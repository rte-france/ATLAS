"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements LazyScenarioMatrix
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Self

import pandas as pd
import pendulum
import polars as pl
from pydantic_core import core_schema

from atlas.io_utils.utils import scan_data_file
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.timing import check_timezone
from atlas.typing import TimeseriesDict


class LazyScenarioMatrix:
    """Base class for lazily storing Timeseries-like data indexed by scenario keys or datetimes."""

    def __init__(self, matrix: pl.LazyFrame | LazyScenarioMatrix | ScenarioMatrix, timezone: str = "UTC") -> None:
        """
        Initialize the LazyScenarioMatrix.

        :param matrix: LazyFrame, ScenarioMatrix, or LazyScenarioMatrix object.
        :type matrix: pl.LazyFrame | LazyScenarioMatrix | ScenarioMatrix
        :param timezone: Timezone for the datetime column.
        :type timezone: str
        """
        check_timezone(timezone)
        self.timezone = timezone

        if isinstance(matrix, LazyScenarioMatrix):
            self.matrix = matrix.get_matrix()
            self.timezone = matrix.timezone
        elif isinstance(matrix, ScenarioMatrix):
            self.matrix = matrix.to_lazy()
            self.timezone = matrix.timezone
        elif isinstance(matrix, pl.LazyFrame):
            schema = matrix.collect_schema()

            time_columns = [name for name, dtype in schema.items() if dtype.is_temporal()]
            value_columns = [name for name, dtype in schema.items() if dtype.is_numeric()]

            if len(time_columns) != 1:
                raise ValueError("LazyScenarioMatrix must have exactly one datetime column")

            if len(time_columns) + len(value_columns) != len(schema):
                raise ValueError("LazyScenarioMatrix must have N columns one for datetime and N-1 for numerical values")

            self.matrix = (
                matrix.rename({time_columns[0]: "time"})
                .with_columns(pl.col("time").cast(pl.Datetime("us", time_zone=self.timezone)))
                .sort("time")
            )
        else:
            raise TypeError("LazyScenarioMatrix requires a LazyFrame, ScenarioMatrix, or LazyScenarioMatrix")

        self.indexes = self._get_indexes()

    @property
    def lazyframe(self) -> pl.LazyFrame:
        """Returns the ScenarioMatrix DataFrame"""
        return self.matrix

    @property
    def index(self) -> list[str]:
        """Returns the ScenarioMatrix indexes (e.g columns names)"""
        return self._get_indexes()

    def __repr__(self):
        """String representation of the ScenarioMatrix"""
        return f"LazyScenarioMatrix with schema : {self.matrix.collect_schema()}"

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        filters: tuple[str, str] | None = None,
        separator: str = ";",
    ) -> LazyScenarioMatrix:
        """
        Load a LazyScenarioMatrix from a file.

        :param file_path: Path to the file
        :param separator: CSV separator (if applicable)
        :param timezone: Timezone to apply
        :return: LazyScenarioMatrix instance
        """

        return cls(scan_data_file(file_path, filters, separator), timezone)

    def get_matrix(self) -> pl.LazyFrame:
        """Return internal lazy frame."""
        return self.matrix

    def collect(self) -> ScenarioMatrix:
        """Collect the lazy frame and return a regular ScenarioMatrix object."""
        return ScenarioMatrix(self.matrix.collect(), timezone=self.timezone)

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

    def set_frequency(self, frequency: str | timedelta | pendulum.Duration, inplace: bool = True) -> Self:
        """
        Change the frequency (timestep) of all scenario time series in the lazy matrix.

        This method collects the lazy frame, applies set_frequency, then converts back to lazy.

        :param frequency: The desired frequency. Can be a string (e.g., '1d', '15m') or a `pendulum.Duration`.
        :type frequency: str or pendulum.Duration
        :param inplace: If True, modifies the object in place. If False, returns a new modified object.
        :type inplace: bool
        :return: The resampled lazy scenario matrix, either modified in place or as a new object.
        :rtype: LazyScenarioMatrix
        """
        resampled_sm = self.collect().set_frequency(frequency, inplace=False)
        if inplace:
            self.matrix = resampled_sm.to_lazy()
            return self
        else:
            return self.__class__(resampled_sm.to_lazy(), timezone=self.timezone)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.is_instance_schema(
            cls,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: "scenario_matrix", when_used="json"
            ),
        )
