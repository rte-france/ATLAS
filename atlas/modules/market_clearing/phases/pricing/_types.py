"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Structural type shared by the first/second/third pricing attempt modules, so they can be
type-checked against `Pricing` without importing it back (`Pricing` imports the attempt modules).
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Protocol

import pendulum

from atlas.modules.market_clearing.data_classes import PriceGroup
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases._helpers import GroupPair
from atlas.solver.solver_interface import OptimisationModel
from atlas.solver.temporal_variable import TemporalVariable


class PricingAttempt(IntEnum):
    """Which pricing attempt `compute_price_bounds` is tightening bounds for: the first attempt bounds
    on both accepted and rejected orders, the second attempt (run when the first is infeasible) on
    accepted orders only."""

    FIRST = 1
    SECOND = 2


@dataclass
class PricingVariables:
    """Temporal variables of the pricing model, filled by the attempts that create them.

    Price groups are rebuilt at every time step and a group id is the index of the market area that
    opens the group: the same id may gather different areas at different times, and only exists at
    some of them (see :func:`~atlas.modules.market_clearing.phases._helpers.times_by_group`). Pair
    families are keyed by the ids of both groups, in the order given by
    :func:`~atlas.modules.market_clearing.phases._helpers.iter_group_pairs`.
    """

    price: dict[int, TemporalVariable] = field(default_factory=dict)
    positive_price: dict[int, TemporalVariable] = field(default_factory=dict)
    negative_price: dict[int, TemporalVariable] = field(default_factory=dict)
    positive_price_diff: dict[GroupPair, TemporalVariable] = field(default_factory=dict)
    negative_price_diff: dict[GroupPair, TemporalVariable] = field(default_factory=dict)
    positive_branch_load_slack: dict[GroupPair, TemporalVariable] = field(default_factory=dict)
    negative_branch_load_slack: dict[GroupPair, TemporalVariable] = field(default_factory=dict)
    shadow_price: dict[str, TemporalVariable] = field(default_factory=dict)
    worst_rejected_sale: dict[int, TemporalVariable] = field(default_factory=dict)
    worst_rejected_buy: dict[int, TemporalVariable] = field(default_factory=dict)


class _PricingPhase(Protocol):
    """Structural type for the `Pricing` state the first/second/third attempt functions read."""

    model: OptimisationModel
    variables: PricingVariables
    parameters: MarketClearingParameters
    input_dataset: MarketClearingInputDataset
    price_groups: dict[pendulum.DateTime, list[PriceGroup]]
    saturated_critical_branch: dict[tuple[str, pendulum.DateTime], float]
    clearing_border_exchanges: dict[tuple[str, pendulum.DateTime], float]
    clearing_accepted_powers: dict[tuple[str, str], float]
    dict_linked_orders: dict[int, list[OrderMC]]
    dict_parent_child_orders: dict[int, tuple[list[OrderMC], list[OrderMC]]]
    _full_link_id_by_order: dict[str, int]

    def is_neighbour(self, price_group: PriceGroup, other_price_group: PriceGroup) -> bool: ...

    def compute_price_bounds(self, price_group: PriceGroup, pricing_type: PricingAttempt) -> None: ...
