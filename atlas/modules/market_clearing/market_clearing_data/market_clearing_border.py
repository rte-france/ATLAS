"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum

from atlas.config import logger
from atlas.math.timeseries import Timeseries
from atlas.models.market.market_border import MarketBorder

# Static definition of default bounds on exchanges (can be changed at will):
DEFAULT_MAX_FLOW = 10000.0
DEFAULT_MIN_FLOW = -10000.0


class MCBorder:
    def __init__(self, border: MarketBorder, times: list[pendulum.DateTime], time_step: int):
        self.border = border
        minute_time_step = pendulum.Duration(minutes=time_step)
        if border.maximum_flow:
            self.max_flow = border.maximum_flow.set_frequency(minute_time_step, False).filter(times)
        else:
            self.max_flow = Timeseries.from_index(times[0], minute_time_step, times[-1], DEFAULT_MAX_FLOW)
        if border.minimum_flow:
            self.min_flow = border.minimum_flow.set_frequency(minute_time_step, False).filter(times)
        else:
            self.min_flow = Timeseries.from_index(times[0], minute_time_step, times[-1], DEFAULT_MIN_FLOW)

        if border.reference_flow:
            reference_flow = border.reference_flow.set_frequency(minute_time_step, False).filter(times)
            self.max_flow -= reference_flow
            self.min_flow -= reference_flow

        self.has_loss_factor = True if self.border.loss_factor > 0 else False

        self.time_resolution = self.border.time_resolution if self.border.time_resolution else time_step
        # Check and adapt if needed the time resolution:
        if self.time_resolution < time_step:
            self.time_resolution = time_step
            logger.info(
                f"The time resolution of the border {self.border.name} has had to be adapted to the time step (it was smaller)."
            )
        else:
            n_time_steps, rest = divmod(self.time_resolution, time_step)
            if rest != 0.0:
                self.time_resolution = (n_time_steps + round(rest, 0)) * time_step
                logger.info(
                    f"The time resolution of the border {self.border.name} has had to be rounded according to the time step."
                )
        # TODO : Check link_generator
        # Add to the market area of uphill and downhill the information of border
