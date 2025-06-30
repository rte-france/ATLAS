"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
import pendulum

from atlas.math.timeseries import Timeseries
from atlas.models.market.market_area import MarketArea
from atlas.modules.market_clearing.market_clearing_data.market_clearing_order import MCOrder


INITIAL_MAX_PRICE = 1.0e8
INITIAL_MIN_PRICE = -1.0e8

class MCMarketArea:
    def __init__(self, market_area: MarketArea, orders: dict[str, MCOrder], times: list[pendulum.DateTime], time_step: int):
        self.market_area = market_area
        self.orders = orders
        minute_time_step = pendulum.Duration(minutes=time_step)
        if market_area.reference_balance:
            self.ref_balance = market_area.reference_balance
        else:
            self.ref_balance = Timeseries.from_index(times[0], minute_time_step, times[-1], 0.0)
        if market_area.maximum_price:
            self.max_price = market_area.maximum_price
        else:
            self.max_price = Timeseries.from_index(times[0], minute_time_step, times[-1], INITIAL_MAX_PRICE)
        if market_area.minimum_price:
            self.min_price = market_area.minimum_price
        else:
            self.min_price = Timeseries.from_index(times[0], minute_time_step, times[-1], INITIAL_MIN_PRICE)
