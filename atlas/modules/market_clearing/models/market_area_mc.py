"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
from pendulum import Duration

from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.market.market_area import MarketArea
from atlas.modules.market_clearing.models.order_mc import OrderMC

INITIAL_MAX_PRICE = 1.0e8
INITIAL_MIN_PRICE = -1.0e8

class MarketAreaMC(MarketArea):
    ref_balance: Timeseries | LazyTimeseries
    max_price: Timeseries | LazyTimeseries
    min_price: Timeseries | LazyTimeseries

    mc_orders: dict[str, OrderMC]

    # Attributes from market clearing parameter
    time_step: Duration
    times: list[pendulum.DateTime]

    @property
    def ref_balance(self) -> Timeseries | LazyTimeseries:
        if self.reference_balance:
            return self.reference_balance.set_frequency(self.time_step, False).filter(self.times)
        else:
            return Timeseries.from_index(self.times[0], self.time_step, self.times[-1], 0.0)

    @property
    def max_price(self) -> Timeseries | LazyTimeseries:
        if self.maximum_price:
            return self.maximum_price.set_frequency(self.time_step, False).filter(self.times)
        else:
            return Timeseries.from_index(self.times[0], self.time_step, self.times[-1], INITIAL_MAX_PRICE)

    @property
    def min_price(self) -> Timeseries | LazyTimeseries:
        if self.minimum_price:
            return self.minimum_price.set_frequency(self.time_step, False).filter(self.times)
        else:
            return Timeseries.from_index(self.times[0], self.time_step, self.times[-1], INITIAL_MIN_PRICE)
