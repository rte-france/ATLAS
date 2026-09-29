"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from atlas.common.optimal_dispatch.input_objects.hydro import HydroDispatchInput
from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix


class HydroPO(HydroDispatchInput):
    maximum_fcr: float
    maximum_afrr: float
    storage_marginal_value: AbstractScenarioMatrix
