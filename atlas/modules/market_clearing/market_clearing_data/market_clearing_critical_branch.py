"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum

from atlas.models.market.critical_branch import CriticalBranch


class MCCriticalBranch:
    def __init__(self, critical_branch: CriticalBranch, times: list[pendulum.DateTime], time_step: int):
        self.critical_branch = critical_branch
        minute_time_step = pendulum.Duration(minutes=time_step)
        if critical_branch.maximum_flow:
            self.max_flow = critical_branch.maximum_flow.set_frequency(minute_time_step, False).filter(times)
        else:
            self.max_flow = None
        if critical_branch.flow_reliability_margin:
            self.flow_reliability_margin = critical_branch.flow_reliability_margin.set_frequency(
                minute_time_step, False
            ).filter(times)
        else:
            self.flow_reliability_margin = None
        if critical_branch.reference_flow:
            self.ref_flow = critical_branch.reference_flow.set_frequency(minute_time_step, False).filter(times)
        else:
            self.ref_flow = None

        if self.max_flow is not None:
            if self.flow_reliability_margin is not None:
                self.max_flow -= self.flow_reliability_margin
            if self.ref_flow is not None:
                self.max_flow -= self.ref_flow

        self.ptdf = self.critical_branch.market_area_ptdf.da_ptdf.set_frequency(minute_time_step, False).filter(times)
