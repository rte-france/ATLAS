"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from functools import cached_property

import pendulum
from pendulum import Duration

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.objects.market.market_area import MarketArea

INITIAL_MAX_PRICE = 1.0e8
INITIAL_MIN_PRICE = -1.0e8


class MarketAreaMC(MarketArea):
    orders: dict[str, OrderMC]

    # Attributes from market clearing parameter
    timestep: Duration
    times: list[pendulum.DateTime]

    @cached_property
    def ref_balance(self) -> AbstractTimeseries:
        if self.reference_balance:
            return self.reference_balance.filter(self.times)
        else:
            return Timeseries.from_index(self.times[0], self.timestep, self.times[-1], 0.0)

    @cached_property
    def max_price(self) -> AbstractTimeseries:
        if self.maximum_price:
            return self.maximum_price.filter(self.times)
        else:
            return Timeseries.from_index(self.times[0], self.timestep, self.times[-1], INITIAL_MAX_PRICE)

    @cached_property
    def min_price(self) -> AbstractTimeseries:
        if self.minimum_price:
            return self.minimum_price.filter(self.times)
        else:
            return Timeseries.from_index(self.times[0], self.timestep, self.times[-1], INITIAL_MIN_PRICE)
