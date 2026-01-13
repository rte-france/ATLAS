"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ScenarioMatrix
"""

import pandas as pd
import polars as pl
from pydantic_core import core_schema

from atlas.math.lazy_matrix import LazyMatrix
from atlas.math.matrix import Matrix


class ScenarioMatrix(Matrix):
    """Eager version of a matrix for managing time series by scenario name.

    Inherits from the `Matrix` class and is backed by a Polars DataFrame.
    Each column after the timestamp represents a time series for a specific scenario.

    This class is intended for workflows where all data can be loaded and processed
    in memory."""

    def __init__(self, matrix: pd.DataFrame | pl.DataFrame | Matrix | None = None, timezone: str = "UTC") -> None:
        super().__init__(matrix, timezone)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.is_instance_schema(
            cls,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: "scenario_matrix", when_used="json"
            ),
        )

    def __repr__(self):
        """Provide a string representation of the Matrix object."""
        return f"Scenario Matrix : {self.matrix}"


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
