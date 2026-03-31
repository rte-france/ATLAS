"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import model_validator

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.models.equipment.load import Load
from atlas.modules.day_ahead_orders.models.portfolio import PortfolioDAO


class LoadDAO(Load):
    portfolio: PortfolioDAO
    variable_cost: AbstractTimeseries

    @model_validator(mode="wrap")
    @classmethod
    def convert_portfolio(cls, value, handler):
        if isinstance(value, Load):
            data = dict(value)
            if value.portfolio:
                data["portfolio"] = PortfolioDAO(**dict(value.portfolio))
            return handler(data)
        return handler(value)
