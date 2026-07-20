"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.objects.market.market_area import MarketArea

INITIAL_MAX_PRICE = 1.0e8
INITIAL_MIN_PRICE = -1.0e8


class MarketAreaMC(MarketArea):
    mc_orders: dict[str, OrderMC]
