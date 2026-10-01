"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Structural type shared by the first/second/third pricing attempt modules, so they can be
type-checked against `Pricing` without importing it back (`Pricing` imports the attempt modules).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Protocol

import pendulum

from atlas.modules.market_clearing.data_classes import PriceGroup
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases._helpers import GroupPair
from atlas.solver.solver_interface import OptimisationModel
from atlas.solver.temporal_variable import TemporalVariable

if TYPE_CHECKING:
    # ortools-stubs does not ship pywraplp (see the solver_interface mypy override)
    from ortools.linear_solver import pywraplp  # type: ignore[attr-defined]


class PricingAttempt(IntEnum):
    """Which pricing attempt `compute_price_bounds` is tightening bounds for: the first attempt bounds
    on both accepted and rejected orders, the second attempt (run when the first is infeasible) on
    accepted orders only."""

    FIRST = 1
    SECOND = 2


@dataclass(frozen=True)
class PricingVariables:
    """Variables of the first pricing attempt, which the later attempts build upon.

    Price groups are rebuilt at every time step and a group id is the index of the market area that
    opens the group: the same id may gather different areas at different times, and only exists at
    some of them (see :func:`~atlas.modules.market_clearing.phases._helpers.times_by_group`). Pair
    families are keyed by the ids of both groups, in the order given by
    :func:`~atlas.modules.market_clearing.phases._helpers.iter_group_pairs`. Branch load slacks only
    exist at the time steps without any saturated critical branch, and are empty without a slack penalty.
    Each accepted child order of a parent-child group gives it a surplus, keyed by child order name.
    """

    price: dict[int, TemporalVariable]
    positive_price: dict[int, TemporalVariable]
    negative_price: dict[int, TemporalVariable]
    positive_price_diff: dict[GroupPair, TemporalVariable]
    negative_price_diff: dict[GroupPair, TemporalVariable]
    positive_branch_load_slack: dict[GroupPair, TemporalVariable]
    negative_branch_load_slack: dict[GroupPair, TemporalVariable]
    shadow_price: dict[str, TemporalVariable]
    child_link_surplus: dict[str, pywraplp.Variable]


@dataclass(frozen=True)
class RejectionVariables:
    """Temporal variables of the second pricing attempt: the surplus of the worst rejected orders of each group."""

    worst_rejected_sale: dict[int, TemporalVariable]
    worst_rejected_buy: dict[int, TemporalVariable]


@dataclass(frozen=True)
class ParadoxVariables:
    """Variables of the third pricing attempt: the paradoxical delta-P of the linked order groups, of the
    parent-child groups with an accepted order, and of the accepted standalone orders."""

    linked_orders: dict[int, pywraplp.Variable]
    parent_child: dict[int, pywraplp.Variable]
    orders: dict[str, pywraplp.Variable]


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
    full_link_id_by_order: dict[str, int]

    def is_accepted(self, order: OrderMC) -> bool: ...

    def order_price(self, order: OrderMC) -> pywraplp.Variable: ...

    def standalone_orders(self) -> Iterator[OrderMC]: ...

    def is_neighbour(self, price_group: PriceGroup, other_price_group: PriceGroup) -> bool: ...

    def compute_price_bounds(self, price_group: PriceGroup, pricing_type: PricingAttempt) -> None: ...
