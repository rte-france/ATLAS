"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas import Equipment, Order


class IntraDayOrder(Order):
    equipment: Equipment
    execution_date: DateTime  # type:ignore[assignment]
    start_date: DateTime  # type:ignore[assignment]
    end_date: DateTime  # type:ignore[assignment]
