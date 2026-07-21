"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from functools import cached_property

from pendulum import DateTime, Duration

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.modules.market_clearing.input_objects.market_area import MarketAreaMC
from atlas.objects.market.market_area_ptdf import MarketAreaPtdf


class MarketAreaPtdfMC(MarketAreaPtdf):
    da_ptdf: AbstractTimeseries
    market_area: MarketAreaMC

    # Attributes from market clearing parameter
    timestep: Duration
    times: list[DateTime]

    @cached_property
    def day_ahead_ptdf(self) -> AbstractTimeseries:
        return self.da_ptdf.filter(self.times)
