"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from pendulum import Duration, DateTime

from atlas import Timeseries, LazyTimeseries
from atlas.models.market.market_area_ptdf import MarketAreaPtdf


class MarketAreaPtdfMC(MarketAreaPtdf):
    da_ptdf: Timeseries | LazyTimeseries

    # Attributes from market clearing parameter
    time_step: Duration
    times: list[DateTime]

    @property
    def day_ahead_ptdf(self) -> Timeseries | LazyTimeseries:
        return self.da_ptdf.set_frequency(self.time_step, False).filter(self.times)