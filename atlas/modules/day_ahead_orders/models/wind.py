"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import model_validator

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.models.equipment.wind import Wind
from atlas.modules.day_ahead_orders.models.portfolio import PortfolioDAO


class WindDAO(Wind):
    portfolio: PortfolioDAO
    maximum_curtailment_ratio: AbstractTimeseries

    @model_validator(mode="wrap")
    @classmethod
    def convert_portfolio(cls, value, handler):
        if isinstance(value, Wind):
            data = dict(value)
            if value.portfolio:
                data["portfolio"] = PortfolioDAO(**dict(value.portfolio))
            return handler(data)
        return handler(value)
