"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic_extra_types.pendulum_dt import DateTime

from atlas.objects.equipment.equipment import Equipment
from atlas.objects.market.order import Order


class OrderDAO(Order):
    equipment: Equipment
    execution_date: DateTime  # type:ignore[assignment]
    start_date: DateTime  # type:ignore[assignment]
    end_date: DateTime  # type:ignore[assignment]
