"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
from pendulum import Duration

from atlas import MarketAreaPtdf
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.market.critical_branch import CriticalBranch


class CriticalBranchMC(CriticalBranch):
    market_area_ptdf: list[MarketAreaPtdf]

    # Attributes from market clearing parameter
    timestep: Duration
    times: list[pendulum.DateTime]

    @property
    def flow_margin(self) -> AbstractTimeseries | None:
        if self.flow_reliability_margin:
            return self.flow_reliability_margin.set_frequency(self.timestep, False).filter(self.times)
        else:
            return None

    @property
    def ref_flow(self) -> AbstractTimeseries | None:
        if self.reference_flow:
            return self.reference_flow.set_frequency(self.timestep, False).filter(self.times)
        else:
            return None

    @property
    def max_flow(self) -> AbstractTimeseries | None:
        if self.maximum_flow:
            max_flow = self.maximum_flow.set_frequency(self.timestep, False).filter(self.times)
            if self.flow_margin is not None:
                max_flow -= self.flow_margin
            if self.ref_flow is not None:
                max_flow -= self.ref_flow
            return max_flow
        else:
            return None
