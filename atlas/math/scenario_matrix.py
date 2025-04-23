"""
Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ScenarioMatrix
"""

from atlas.math.matrix import Matrix
from atlas.math.timeseries import Timeseries


class ScenarioMatrix(Matrix):
    """Stores Timeseries objects by scenario name, with access and deletion by name."""

    def __init__(self, name: str, indexes: list[str | int | float], timeseries: list[Timeseries]):
        super().__init__(name, indexes, timeseries)
