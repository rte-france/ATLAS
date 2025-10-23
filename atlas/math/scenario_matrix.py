"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ScenarioMatrix
"""

from typing import Literal, cast

import pandas as pd
import pendulum
import polars as pl

from atlas.math.lazy_matrix import LazyMatrix
from atlas.math.matrix import Matrix
from atlas.timing import get_duration, infer_frequency


class ScenarioMatrix(Matrix):
    """Eager version of a matrix for managing time series by scenario name.

    Inherits from the `Matrix` class and is backed by a Polars DataFrame.
    Each column after the timestamp represents a time series for a specific scenario.

    This class is intended for workflows where all data can be loaded and processed
    in memory."""

    def __init__(self, matrix: pd.DataFrame | pl.DataFrame | Matrix | None = None, timezone: str = "UTC") -> None:
        super().__init__(matrix, timezone)

    def __repr__(self):
        """Provide a string representation of the Matrix object."""
        return f"Scenario Matrix : {self.matrix}"

    def set_frequency(self, frequency: str | pendulum.Duration, inplace: bool = True) -> "ScenarioMatrix":
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
            return self if inplace else ScenarioMatrix(self.matrix.clone(), self.timezone)

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
            return ScenarioMatrix(df, self.timezone)

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


class LazyScenarioMatrix(LazyMatrix):
    """Lazy version of a matrix for managing time series by scenario name.

    Inherits from the `LazyMatrix` class and is backed by a Polars LazyFrame.
    Useful for large-scale data pipelines or deferred execution scenarios."""

    def __init__(self, matrix: pl.LazyFrame | Matrix | LazyMatrix, timezone: str = "UTC") -> None:
        super().__init__(matrix, timezone)

    def __repr__(self):
        """String representation of the matrix"""
        return f"LazyScenarioMatrix with schema : {self.matrix.collect_schema()}"

    def collect(self) -> Matrix:
        """Collect the lazy frame and return a regular ScenarioMatrix object."""
        return ScenarioMatrix(self.matrix.collect(), timezone=self.timezone)

    def set_frequency(self, frequency: str | pendulum.Duration, inplace: bool = True) -> "LazyScenarioMatrix":
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
        resampled_sm = cast(ScenarioMatrix, self.collect()).set_frequency(frequency, inplace=False)
        if inplace:
            self.matrix = resampled_sm.to_lazy()
            return self
        else:
            return LazyScenarioMatrix(resampled_sm.to_lazy(), timezone=self.timezone)
