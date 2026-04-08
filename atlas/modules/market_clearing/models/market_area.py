"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
from pendulum import Duration

from atlas import ControlBlock
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.timeseries import Timeseries
from atlas.objects.market.market_area import MarketArea
from atlas.modules.market_clearing.models.order import OrderMC

INITIAL_MAX_PRICE = 1.0e8
INITIAL_MIN_PRICE = -1.0e8


class MarketAreaMC(MarketArea):
    control_block: ControlBlock

    mc_orders: dict[str, OrderMC]

    # Attributes from market clearing parameter
    timestep: Duration
    times: list[pendulum.DateTime]

    @property
    def ref_balance(self) -> AbstractTimeseries:
        if self.reference_balance:
            return self.reference_balance.set_frequency(self.timestep, False).filter(self.times)
        else:
            return Timeseries.from_index(self.times[0], self.timestep, self.times[-1], 0.0)

    @property
    def max_price(self) -> AbstractTimeseries:
        if self.maximum_price:
            return self.maximum_price.set_frequency(self.timestep, False).filter(self.times)
        else:
            return Timeseries.from_index(self.times[0], self.timestep, self.times[-1], INITIAL_MAX_PRICE)

    @property
    def min_price(self) -> AbstractTimeseries:
        if self.minimum_price:
            return self.minimum_price.set_frequency(self.timestep, False).filter(self.times)
        else:
            return Timeseries.from_index(self.times[0], self.timestep, self.times[-1], INITIAL_MIN_PRICE)
