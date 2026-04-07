"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import Duration
from pydantic import model_validator

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.models.equipment.thermal import Thermal
from atlas.modules.day_ahead_orders.models.portfolio import PortfolioDAO


class ThermalDAO(Thermal):
    portfolio: PortfolioDAO
    variable_cost: AbstractTimeseries
    startup_cost: AbstractTimeseries
    minimum_time_on: Duration
    maximum_power: AbstractTimeseries
    minimum_power: AbstractTimeseries
    minimum_stable_power_duration: Duration
    minimum_time_off: Duration
    additional_hours: Duration

    @model_validator(mode="before")
    @classmethod
    def convert_portfolio(cls, value):
        if isinstance(value, Thermal) and value.portfolio:
            data = dict(value)
            data["portfolio"] = PortfolioDAO(**dict(value.portfolio))
            return data
        return value
