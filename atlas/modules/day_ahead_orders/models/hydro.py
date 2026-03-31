"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import model_validator

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
    fragment_prices: list[float]
    fragment_volumes: list[float]

    @model_validator(mode="wrap")
    @classmethod
    def convert_portfolio(cls, value, handler):
        if isinstance(value, Hydro):
            data = dict(value)
            if value.portfolio:
                data["portfolio"] = PortfolioDAO(**dict(value.portfolio))
            return handler(data)
        return handler(value)
