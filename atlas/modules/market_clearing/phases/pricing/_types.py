"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Structural type shared by the first/second/third pricing pass modules, so they can be
type-checked against `Pricing` without importing it back (`Pricing` imports the pass modules).
"""

from enum import IntEnum
from typing import Protocol

from atlas.modules.market_clearing.data_classes import PriceGroup
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.objects.market.order import Order
from atlas.solver.solver_interface import OptimisationModel


class PricingPass(IntEnum):
    """Which pricing pass `compute_price_bounds` is tightening bounds for: the first pass bounds
    on both accepted and rejected orders, the second pass on accepted orders only."""

    FIRST = 1
    SECOND = 2


class _PricingPhase(Protocol):
    """Structural type for the `Pricing` state the first/second/third pass functions read."""

    model: OptimisationModel
    parameters: MarketClearingParameters
    input_dataset: MarketClearingInputDataset
    price_groups: dict[int, list[PriceGroup]]
    saturated_critical_branch: dict[tuple[str, int], float]
    clearing_border_exchanges: dict[tuple[str, int], float]
    clearing_accepted_powers: dict[tuple[str, str], float]
    dict_linked_orders: dict[int, list[Order]]
    dict_parent_child_orders: dict[int, tuple[list[Order], list[Order]]]
    _full_link_id_by_order: dict[str, int]

    def is_neighbour(self, price_group: PriceGroup, other_price_group: PriceGroup) -> bool: ...

    def compute_price_bounds(self, price_group: PriceGroup, pricing_type: PricingPass) -> None: ...
