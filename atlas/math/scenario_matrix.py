"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ScenarioMatrix
"""

import pandas as pd
import polars as pl

from atlas.math.lazy_matrix import LazyMatrix
from atlas.math.matrix import Matrix


class ScenarioMatrix(Matrix):
    """Stores Timeseries objects by scenario name, with access and deletion by name."""

    def __init__(self, matrix: pd.DataFrame | pl.DataFrame) -> None:
        super().__init__(matrix)


class LazyScenarioMatrix(LazyMatrix):
    """Stores Timeseries objects lazily by scenario name, with access and deletion by name."""

    def __init__(self, matrix: pl.DataFrame | pl.LazyFrame | ScenarioMatrix) -> None:
        super().__init__(matrix)
