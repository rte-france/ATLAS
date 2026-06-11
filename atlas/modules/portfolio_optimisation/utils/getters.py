"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.input_objects import EquipmentPO


def get_variable_cost(obj: EquipmentPO, time: DateTime):
    """
    Get variable cost for equipment at specified time.

    :param obj: Equipment object
    :type obj: EquipmentPO
    :param time: Current time period
    :type time: DateTime
    :return: Variable cost value
    :rtype: float
    """
    if obj.variable_cost is not None:
        return obj.variable_cost.get_value(time)
    return 0.0


def get_maximum_automated(obj: EquipmentPO) -> float:
    """
    Get maximum automated reserve capacity for equipment.

    :param obj: Equipment object
    :type obj: EquipmentPO
    :return: Maximum automated reserve (sum of AFRR and FCR)
    :rtype: float
    """
    return (obj.maximum_afrr or 0.0) + (obj.maximum_fcr or 0.0)
