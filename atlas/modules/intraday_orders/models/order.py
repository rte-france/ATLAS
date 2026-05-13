"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic_extra_types.pendulum_dt import DateTime

from atlas import Equipment, Order


class IntraDayOrder(Order):
    equipment: Equipment
    execution_date: DateTime
    start_date: DateTime
    end_date: DateTime
