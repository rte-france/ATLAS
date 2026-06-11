"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime, Duration

from atlas.core.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.market.market_area_ptdf import MarketAreaPtdf


class MarketAreaPtdfMC(MarketAreaPtdf):
    da_ptdf: AbstractTimeseries

    # Attributes from market clearing parameter
    timestep: Duration
    times: list[DateTime]

    @property
    def day_ahead_ptdf(self) -> AbstractTimeseries:
        return self.da_ptdf.set_frequency(self.timestep, False).filter(self.times)
