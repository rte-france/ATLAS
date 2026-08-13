"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from dataclasses import dataclass, field

from pendulum import DateTime

from atlas.modules.day_ahead_orders.steps.result import EquipmentOptimisationResult


@dataclass
class StorageOptimisationResult(EquipmentOptimisationResult):
    """
    Direct LP solver output for a storage unit — variable values extracted after solve().

    Intentionally free of business logic: no prices, no orders, no Timeseries.
    Everything downstream (price calculation, order creation) is handled by
    :class:`~atlas.common.optimal_dispatch.order_builder.AbstractOrderBuilder`.

    :param sell_volumes: Sell (discharge) power per timestep in MW.
    :param buy_volumes: Buy (charge) power per timestep in MW (positive convention).
    """

    sell_volumes: dict[DateTime, float] = field(default_factory=dict)
    buy_volumes: dict[DateTime, float] = field(default_factory=dict)
