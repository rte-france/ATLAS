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

    @model_validator(mode="before")
    @classmethod
    def convert_portfolio(cls, value):
        if isinstance(value, Wind) and value.portfolio:
            data = dict(value)
            data["portfolio"] = PortfolioDAO(**dict(value.portfolio))
            return data
        return value
