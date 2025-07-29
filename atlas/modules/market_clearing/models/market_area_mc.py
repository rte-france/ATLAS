"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
from pendulum._pendulum import Duration

from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.market.market_area import MarketArea

INITIAL_MAX_PRICE = 1.0e8
INITIAL_MIN_PRICE = -1.0e8

class MarketAreaMC(MarketArea):
    ref_balance: Timeseries | LazyTimeseries | None = None
    max_price: Timeseries | LazyTimeseries | None = None
    min_price: Timeseries | LazyTimeseries | None = None

    def compute_attributes(self, times: list[pendulum.DateTime], time_step: Duration):
        if self.reference_balance:
            self.ref_balance = self.reference_balance.set_frequency(time_step, False).filter(times)
        else:
            self.ref_balance = Timeseries.from_index(times[0], time_step, times[-1], 0.0)
        if self.maximum_price:
            self.max_price = self.maximum_price.set_frequency(time_step, False).filter(times)
        else:
            self.max_price = Timeseries.from_index(times[0], time_step, times[-1], INITIAL_MAX_PRICE)
        if self.minimum_price:
            self.min_price = self.minimum_price.set_frequency(time_step, False).filter(times)
        else:
            self.min_price = Timeseries.from_index(times[0], time_step, times[-1], INITIAL_MIN_PRICE)