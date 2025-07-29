"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
import pendulum
from pendulum import Duration

from atlas import Timeseries, LazyTimeseries
from atlas.config import logger
from atlas.models.market.market_border import MarketBorder

# Static definition of default bounds on exchanges (can be changed at will):
DEFAULT_MAX_FLOW = 10000.0
DEFAULT_MIN_FLOW = -10000.0


class MarketBorderMC(MarketBorder):
    # Attributes from market clearing parameter
    time_step: Duration
    times: list[pendulum.DateTime]

    @property
    def max_flow(self) -> Timeseries | LazyTimeseries:
        if self.maximum_flow:
            max_flow = self.maximum_flow.set_frequency(self.time_step, False).filter(self.times)
        else:
            max_flow = Timeseries.from_index(self.times[0], self.time_step, self.times[-1], DEFAULT_MAX_FLOW)
        max_flow -= self.ref_flow
        return max_flow

    @property
    def min_flow(self) -> Timeseries | LazyTimeseries:

        if self.maximum_price:
            min_flow = self.minimum_flow.set_frequency(self.time_step, False).filter(self.times)
        else:
            min_flow = Timeseries.from_index(self.times[0], self.time_step, self.times[-1], DEFAULT_MIN_FLOW)
        min_flow -= self.ref_flow
        return min_flow

    @property
    def ref_flow(self) -> Timeseries | LazyTimeseries |None:
        if self.reference_flow:
            return self.reference_flow.set_frequency(self.time_step, False).filter(self.times)

    @property
    def has_loss_factor(self) -> bool:
        return True if self.loss_factor > 0 else False

    @property
    def time_resolution(self) -> int:
        time_resolution = self.border.time_resolution if self.border.time_resolution else self.time_step
        # Check and adapt if needed the time resolution:
        if self.time_resolution < self.time_step.total_minutes():
            time_resolution = self.time_step
            logger.info(
                f"The time resolution of the border {self.border.name} has had to be adapted to the time step (it was smaller)."
            )
        else:
            n_time_steps, rest = divmod(time_resolution, self.time_step.total_minutes())
            if rest != 0.0:
                time_resolution = (n_time_steps + round(rest)) * self.time_step.total_minutes()
                logger.info(
                    f"The time resolution of the border {self.border.name} has had to be rounded according to the time step."
                )
        return time_resolution