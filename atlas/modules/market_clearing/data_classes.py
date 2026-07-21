"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Plain data containers shared across the market_clearing module and its phases.
"""

from dataclasses import dataclass, field

from atlas.objects.market.order import Order


@dataclass
class PriceGroup:
    id: int
    time_index: int
    market_area_names: list[str] = field(default_factory=list)
    max_price: float = float("inf")
    min_price: float = -float("inf")
    min_rejected_sale: float = float("inf")
    max_rejected_buy: float = -float("inf")


@dataclass(frozen=True)
class OrderLinks:
    """Immutable result of resolving a dataset's order couplings.

    :param linked_orders: index -> orders sharing a IDENTICAL_VOLUME/IDENTICAL_RATIO/COMPLEMENT
        link (including circular parent-child groups folded into a link).
    :param parent_child_orders: index -> (parent orders, child orders) for each PARENT_CHILDREN
        group.
    :param full_link_id_by_order: order name -> the key into ``linked_orders`` it belongs to.
    :param full_pc_id_by_order: order name -> the key into ``parent_child_orders`` it belongs to.
    :param child_id_by_order: order name -> its rank among the children of its parent-child group.
    :param circular_pc_id_by_order: order name -> the id of the circular parent-child group it
        belongs to, before that group was folded into ``linked_orders``.
    """

    linked_orders: dict[int, list[Order]]
    parent_child_orders: dict[int, tuple[list[Order], list[Order]]]
    full_link_id_by_order: dict[str, int] = field(default_factory=dict)
    full_pc_id_by_order: dict[str, int] = field(default_factory=dict)
    child_id_by_order: dict[str, str] = field(default_factory=dict)
    circular_pc_id_by_order: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class IdvIdrCouplingIndex:
    """Index of IDENTICAL_VOLUME/IDENTICAL_RATIO order couplings, built once by
    `OrderLinkResolver._partition_couplings_for_linking` and threaded through the recursive
    resolution of linked-bid groups.

    :param orders_by_coupling: coupling name -> names of the orders it couples.
    :param couplings_by_order: order name -> names of every IDV/IDR coupling it's part of.
    """

    orders_by_coupling: dict[str, list[str]]
    couplings_by_order: dict[str, list[str]]


@dataclass(frozen=True)
class ClearingOutputs:
    """Results of the Clearing and ExchangesFixing phases, consumed by Pricing and by the
    market clearing output dataset."""

    saturated_critical_branch: dict[tuple[str, int], float]
    border_exchanges: dict[tuple[str, int], float]
    local_balances: dict[tuple[str, int], float]
    accepted_powers: dict[tuple[str, str], float]
