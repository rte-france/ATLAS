"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum

from atlas.objects.market.market_border import MarketBorder

# Static definition of default bounds on exchanges (can be changed at will):
DEFAULT_MAX_FLOW = 10000.0
DEFAULT_MIN_FLOW = -10000.0


class MarketBorderMC(MarketBorder):
    @property
    def has_loss_factor(self) -> bool:
        return True if self.loss_factor > 0 else False


def get_max_flow(mc_border: MarketBorderMC, time: pendulum.DateTime) -> float:
    max_flow = mc_border.maximum_flow.get_value(time) if mc_border.maximum_flow else DEFAULT_MAX_FLOW
    if mc_border.reference_flow:
        max_flow -= mc_border.reference_flow.get_value(time)
    return max_flow


def get_min_flow(mc_border: MarketBorderMC, time: pendulum.DateTime) -> float:
    min_flow = mc_border.minimum_flow.get_value(time) if mc_border.minimum_flow else DEFAULT_MIN_FLOW
    if mc_border.reference_flow:
        min_flow -= mc_border.reference_flow.get_value(time)
    return min_flow
