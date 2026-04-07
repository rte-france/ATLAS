"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.models.equipment.solar import Solar
from atlas.modules.day_ahead_orders.models.portfolio import PortfolioDAO


class SolarDAO(Solar):
    portfolio: PortfolioDAO
    maximum_curtailment_ratio: AbstractTimeseries
