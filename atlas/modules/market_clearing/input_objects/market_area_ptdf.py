"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.market.market_area_ptdf import MarketAreaPtdf


class MarketAreaPtdfMC(MarketAreaPtdf):
    # In MC context da_ptdf is always populated (get_market_area_ptdfs assumes it).
    da_ptdf: AbstractTimeseries
