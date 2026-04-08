"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
from pendulum import Duration

from atlas import MarketArea, Timeseries
from atlas.config import logger
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.market.market_border import MarketBorder

# Static definition of default bounds on exchanges (can be changed at will):
DEFAULT_MAX_FLOW = 10000.0
DEFAULT_MIN_FLOW = -10000.0


class MarketBorderMC(MarketBorder):
    uphill_market_area: MarketArea
    downhill_market_area: MarketArea

    # Attributes from market clearing parameter
    timestep: Duration
    times: list[pendulum.DateTime]

    @property
    def max_flow(self) -> AbstractTimeseries:
        if self.maximum_flow:
            max_flow = self.maximum_flow.set_frequency(self.timestep, False).filter(self.times)
        else:
            max_flow = Timeseries.from_index(self.times[0], self.timestep, self.times[-1], DEFAULT_MAX_FLOW)
        if self.ref_flow:
            max_flow -= self.ref_flow
        return max_flow

    @property
    def min_flow(self) -> AbstractTimeseries:
        if self.minimum_flow:
            min_flow = self.minimum_flow.set_frequency(self.timestep, False).filter(self.times)
        else:
            min_flow = Timeseries.from_index(self.times[0], self.timestep, self.times[-1], DEFAULT_MIN_FLOW)
        if self.ref_flow:
            min_flow -= self.ref_flow
        return min_flow

    @property
    def ref_flow(self) -> AbstractTimeseries | None:
        if self.reference_flow:
            return self.reference_flow.set_frequency(self.timestep, False).filter(self.times)
        return None

    @property
    def has_loss_factor(self) -> bool:
        return True if self.loss_factor > 0 else False

    @property
    def resolution_time(self) -> int:
        timestep = self.timestep.total_minutes()
        time_resolution = self.time_resolution if self.time_resolution else timestep
        # Check and adapt if needed the time resolution:
        if self.time_resolution < timestep:
            time_resolution = timestep
            logger.info(
                f"The time resolution of the border {self.name} has had to be adapted to the time step (it was smaller)."
            )
        else:
            n_timesteps, rest = divmod(time_resolution, timestep)
            if rest != 0.0:
                time_resolution = (n_timesteps + round(rest)) * timestep
                logger.info(
                    f"The time resolution of the border {self.name} has had to be rounded according to the time step."
                )
        return int(time_resolution)
