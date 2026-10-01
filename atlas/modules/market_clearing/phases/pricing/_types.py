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


@dataclass(frozen=True)
class PricingVariables:
    """Temporal variables of the first pricing attempt, which the later attempts build upon.

    Price groups are rebuilt at every time step and a group id is the index of the market area that
    opens the group: the same id may gather different areas at different times, and only exists at
    some of them (see :func:`~atlas.modules.market_clearing.phases._helpers.times_by_group`). Pair
    families are keyed by the ids of both groups, in the order given by
    :func:`~atlas.modules.market_clearing.phases._helpers.iter_group_pairs`.

    :param price: Price of each group
    :param positive_price: Positive part of the price of each group
    :param negative_price: Negative part of the price of each group
    :param positive_price_diff: Positive part of the price difference of each pair of groups
    :param negative_price_diff: Negative part of the price difference of each pair of groups
    :param positive_branch_load_slack: Positive slack of the branch load of each pair of groups, only
        at the time steps without any saturated critical branch. Empty without a slack penalty.
    :param negative_branch_load_slack: Negative counterpart of *positive_branch_load_slack*
    :param shadow_price: Shadow price of each critical branch, keyed by branch name
    """

    price: dict[int, TemporalVariable]
    positive_price: dict[int, TemporalVariable]
    negative_price: dict[int, TemporalVariable]
    positive_price_diff: dict[GroupPair, TemporalVariable]
    negative_price_diff: dict[GroupPair, TemporalVariable]
    positive_branch_load_slack: dict[GroupPair, TemporalVariable]
    negative_branch_load_slack: dict[GroupPair, TemporalVariable]
    shadow_price: dict[str, TemporalVariable]


@dataclass(frozen=True)
class RejectionVariables:
    """Temporal variables of the second pricing attempt: the surplus of the worst rejected orders of each group."""

    worst_rejected_sale: dict[int, TemporalVariable]
    worst_rejected_buy: dict[int, TemporalVariable]


@dataclass(frozen=True)
class RelaxableConstraints:
    """Names of the first attempt constraints that the later attempts relax, recorded as they are created.

    Relaxing exactly what was created spares the later attempts from re-deriving the creation
    conditions, and from deactivating a constraint that was never created.

    :param null_marginal_order: Null surplus of the marginally accepted orders, relaxed by the second attempt
    :param linked_orders_surplus: Positive surplus of each group of linked orders, relaxed by the third attempt
    :param parent_child_surplus: Surplus of the parent-child groups, children and parents, relaxed by the
        third attempt
    :param order_surplus: Positive surplus of the accepted orders, relaxed by the third attempt
    """

    null_marginal_order: list[str] = field(default_factory=list)
    linked_orders_surplus: list[str] = field(default_factory=list)
    parent_child_surplus: list[str] = field(default_factory=list)
    order_surplus: list[str] = field(default_factory=list)


class _PricingPhase(Protocol):
    """Structural type for the `Pricing` state the first/second/third attempt functions read."""

    model: OptimisationModel
    variables: PricingVariables
    relaxable: RelaxableConstraints
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
