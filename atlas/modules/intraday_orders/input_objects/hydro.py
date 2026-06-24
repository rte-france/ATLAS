"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.equipment.hydro import Hydro


class HydroIDO(Hydro):
    fragment_volumes: list[float]
    fragment_prices: list[float]
    initial_level: AbstractTimeseries
    storage_marginal_value: AbstractScenarioMatrix
    maximum_power: AbstractTimeseries
    da_cleared_quantity: AbstractTimeseries
