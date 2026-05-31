"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from dataclasses import dataclass, field

from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO


@dataclass
class EquipmentOptimisationResult:
    """
    Base for direct LP solver outputs, per equipment.

    Subclass for each equipment type to add the specific extracted variables
    (e.g. :class:`~atlas.modules.day_ahead_orders.steps.storage.optimisation_result.StorageOptimisationResult`,
    :class:`~atlas.modules.day_ahead_orders.steps.thermal.optimisation_result.ThermalOptimisationResult`).
    """


@dataclass
class BiddingResult:
    """
    Aggregated output of a bidding step — all orders and couplings produced across units.

    Returned by :meth:`~atlas.modules.day_ahead_orders.steps.abstract_step.AbstractBiddingStep.formulate`.
    """

    orders: list[OrderDAO] = field(default_factory=list)
    order_couplings: list[OrderCouplingDAO] = field(default_factory=list)
