"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum

from atlas.objects.market.critical_branch import CriticalBranch


class CriticalBranchMC(CriticalBranch):
    pass


def get_max_flow(mc_critical_branch: CriticalBranchMC, time: pendulum.DateTime) -> float | None:
    if not mc_critical_branch.maximum_flow:
        return None
    max_flow = mc_critical_branch.maximum_flow.get_value(time)
    if mc_critical_branch.flow_reliability_margin:
        max_flow -= mc_critical_branch.flow_reliability_margin.get_value(time)
    if mc_critical_branch.reference_flow:
        max_flow -= mc_critical_branch.reference_flow.get_value(time)
    return max_flow
