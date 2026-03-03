"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.models.equipment.hydro import Hydro
from atlas.modules.day_ahead_orders.models.portfolio import PortfolioDAO


class HydroDAO(Hydro):
    portfolio: PortfolioDAO
    maximum_energy: AbstractTimeseries
    minimum_energy: AbstractTimeseries
    initial_level: AbstractTimeseries
    storage_marginal_value: AbstractScenarioMatrix
    maximum_power: AbstractTimeseries
    maximum_curtailment_ratio: AbstractTimeseries
    fragment_prices: list[float]
    fragment_volumes: list[float]
