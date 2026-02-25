"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import Hydro, LazyTimeseries, ScenarioMatrix, Timeseries
from atlas.modules.day_ahead_orders.models.portfolio import PortfolioDAO


class HydroDAO(Hydro):
    portfolio: PortfolioDAO
    maximum_energy: Timeseries | LazyTimeseries
    minimum_energy: Timeseries | LazyTimeseries
    initial_level: Timeseries | LazyTimeseries
    storage_marginal_value: ScenarioMatrix
    maximum_power: Timeseries | LazyTimeseries
    maximum_curtailment_ratio: Timeseries | LazyTimeseries
    fragment_prices: list[float]
    fragment_volumes: list[float]
