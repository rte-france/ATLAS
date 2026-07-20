"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum

from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.objects.market.market_area import MarketArea

INITIAL_MAX_PRICE = 1.0e8
INITIAL_MIN_PRICE = -1.0e8


class MarketAreaMC(MarketArea):
    mc_orders: dict[str, OrderMC]


def get_ref_balance(mc_market_area: MarketAreaMC, time: pendulum.DateTime) -> float:
    return mc_market_area.reference_balance.get_value(time) if mc_market_area.reference_balance else 0.0


def get_max_price(mc_market_area: MarketAreaMC, time: pendulum.DateTime) -> float:
    return mc_market_area.maximum_price.get_value(time) if mc_market_area.maximum_price else INITIAL_MAX_PRICE


def get_min_price(mc_market_area: MarketAreaMC, time: pendulum.DateTime) -> float:
    return mc_market_area.minimum_price.get_value(time) if mc_market_area.minimum_price else INITIAL_MIN_PRICE
