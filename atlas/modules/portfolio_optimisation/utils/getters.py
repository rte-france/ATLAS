"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.models import EquipmentPO


def get_variable_cost(obj: EquipmentPO, time: DateTime):
    if obj.variable_cost is not None:
        return obj.variable_cost.get_value(time)
    return 0.0


def get_maximum_automated(obj: EquipmentPO) -> float:
    return (obj.maximum_afrr or 0.0) + (obj.maximum_fcr or 0.0)
