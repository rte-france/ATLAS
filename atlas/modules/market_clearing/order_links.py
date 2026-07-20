"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Resolves order couplings (IDENTICAL_VOLUME, IDENTICAL_RATIO, COMPLEMENT, PARENT_CHILDREN) into the
linked-bids and parent-child sets the pricing phase needs.

Extracted from Pricing per ATLAS-296 (PR-5, step 1). The algorithms are unchanged; only the
bookkeeping changed. Previously, resolving these couplings wrote full_link_id, full_pc_id,
child_id and circular_pc_id directly onto the shared OrderMC instances (read by Clearing,
ExchangesFixing, output_dataset.py, ...), coupling every phase to Pricing's internal resolution
order through those side effects. This module keeps that bookkeeping local to one
OrderLinkResolver instance and returns it as part of an immutable OrderLinks result instead.
"""

from dataclasses import dataclass, field

from atlas.config import logger
from atlas.enums import ComplementDirection, CouplingType
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.input_objects.order_coupling import OrderCouplingMC
from atlas.objects.market.order import Order


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


class OrderLinkResolver:
    """Resolves the order couplings of a market_clearing dataset into linked/parent-child sets."""

    def __init__(self, mc_orders: dict[str, OrderMC], mc_order_couplings: dict[str, OrderCouplingMC]):
        self._mc_orders = mc_orders
        self._mc_order_couplings = mc_order_couplings
        self._circular_pc_id: dict[str, int] = {}
        self._full_link_id: dict[str, int] = {}
        self._full_pc_id: dict[str, int] = {}
        self._child_id: dict[str, str] = {}

    def resolve(self) -> OrderLinks:
        circular_children_bids = self._get_circular_parent_child_sets()
        linked_orders = self._compute_linked_bids_sets(circular_children_bids)
        parent_child_orders = self._compute_parent_child_sets(linked_orders)
        return OrderLinks(
            linked_orders=linked_orders,
            parent_child_orders=parent_child_orders,
            full_link_id_by_order=dict(self._full_link_id),
            full_pc_id_by_order=dict(self._full_pc_id),
            child_id_by_order=dict(self._child_id),
            circular_pc_id_by_order=dict(self._circular_pc_id),
        )

    # Defines the global circular parent_child sets and stores them in a dictionary
    def _get_circular_parent_child_sets(self) -> dict[int, list[Order]]:
        dict_circular_children_bids: dict[int, list[Order]] = {}
        index_pc_t = 0

        # Step 1 - Filling the dictionary with unique circular PC linked sets
        for mc_order_coupling in self._mc_order_couplings.values():
            if mc_order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                list_children = [mc_order_coupling.orders[0]]
                circular_orders = self._get_circular_children(mc_order_coupling, list_children, [])
                if len(circular_orders) > 1 and circular_orders not in dict_circular_children_bids.values():
                    dict_circular_children_bids[index_pc_t] = circular_orders
                    index_pc_t += 1

        # Step 2 - Attributing this unique ID to each order present within a set
        for index_pc_t, orders in dict_circular_children_bids.items():
            for order in orders:
                if order.name not in self._circular_pc_id:
                    self._circular_pc_id[order.name] = index_pc_t

        logger.debug(f"'Circular parent child bids sets are : {dict_circular_children_bids}")
        return dict_circular_children_bids

    # Recursively gets all the children from circular parent_child couplings
    def _get_circular_children(
        self, mc_order_coupling: OrderCouplingMC, orders: list[Order], processed_order_couplings: list[str]
    ) -> list[Order]:
        parent_order, child_order = mc_order_coupling.orders[:2]
        child_mc_order = self._mc_orders[child_order.name]
        processed_order_couplings.append(mc_order_coupling.name)
        order_coupling_parent_ids = child_mc_order.order_coupling_parent_ids

        # A parent/child link is considered transitive when the child is also a parent elsewhere
        if child_mc_order.is_parent and order_coupling_parent_ids:
            orders.append(child_order)
            for mc_order_coupling_name in order_coupling_parent_ids:
                if mc_order_coupling_name not in processed_order_couplings:
                    self._get_circular_children(mc_order_coupling, orders, processed_order_couplings)
            return orders
        # The child is not a parent, the transitive parent/child link stops here
        return orders

    def _get_idv_idr_block_sets_fast(
        self,
        order_coupling: OrderCouplingMC,
        block_idv_idr_bids: list[OrderMC],
        treated_order_couplings: list[str],
        index_lo: int,
        idr_idv_coupling_infos: dict[str, list[str]],
        idr_idv_order_couplings: dict[str, list[str]],
    ) -> tuple[list[OrderMC], list[str]]:
        for order_name in idr_idv_coupling_infos[order_coupling.name]:
            mc_order = self._mc_orders[order_name]
            block_idv_idr_bids.append(mc_order)
            self._full_link_id[order_name] = index_lo

            if order_name in idr_idv_order_couplings:
                for linked_order_coupling_name in idr_idv_order_couplings[order_name]:
                    if linked_order_coupling_name in treated_order_couplings:
                        continue
                    treated_order_couplings.append(linked_order_coupling_name)
                    linked_order_coupling = self._mc_order_couplings[linked_order_coupling_name]
                    block_idv_idr_bids, treated_order_couplings = self._get_idv_idr_block_sets_fast(
                        linked_order_coupling,
                        block_idv_idr_bids,
                        treated_order_couplings,
                        index_lo,
                        idr_idv_coupling_infos,
                        idr_idv_order_couplings,
                    )

        return block_idv_idr_bids, treated_order_couplings

    # Defining linked bids sets
    # Finds global links between orders (including circular parent_child links), defines the resulting sets and stores
    # them in a dictionary
    def _compute_linked_bids_sets(self, dict_circular_children_bids: dict[int, list[Order]]) -> dict[int, list[Order]]:
        dict_linked_bids: dict[int, list[Order]] = {}
        index_lo = 0
        treated_order_couplings: list[str] = []

        # Begin by creating two dicts:
        # _ a dict containing, for each IDR or IDV coupling, associated order ids
        # _ a dict containing, for each order, ids of all associated IDR or IDV couplings
        complement_coupling_list = []
        idr_idv_coupling_infos: dict[str, list[str]] = {}
        idr_idv_order_couplings: dict[str, list[str]] = {}
        for mc_order_coupling in self._mc_order_couplings.values():
            if mc_order_coupling.coupling_type == CouplingType.COMPLEMENT:
                complement_coupling_list.append(mc_order_coupling)
                continue
            elif not (
                mc_order_coupling.coupling_type == CouplingType.IDENTICAL_VOLUME
                or mc_order_coupling.coupling_type == CouplingType.IDENTICAL_RATIO
            ):
                continue

            idr_idv_coupling_infos[mc_order_coupling.name] = []
            for order in mc_order_coupling.orders:
                idr_idv_coupling_infos[mc_order_coupling.name].append(order.name)
                if order.name in idr_idv_order_couplings:
                    idr_idv_order_couplings[order.name].append(mc_order_coupling.name)
                else:
                    idr_idv_order_couplings[order.name] = [mc_order_coupling.name]

        for order_coupling_name in idr_idv_coupling_infos:
            mc_order_coupling = self._mc_order_couplings[order_coupling_name]
            # Check if we have already treated this order coupling
            # (Could be the case in a idv or idr block)
            if order_coupling_name in treated_order_couplings:
                continue
            treated_order_couplings.append(order_coupling_name)
            linked_bids = mc_order_coupling.orders
            circularly_linked_bids = []
            block_idv_idr_bids: list[OrderMC] = []
            block_idv_idr_bids, treated_order_couplings = self._get_idv_idr_block_sets_fast(
                mc_order_coupling,
                block_idv_idr_bids,
                treated_order_couplings,
                index_lo,
                idr_idv_coupling_infos,
                idr_idv_order_couplings,
            )

            for linked_order in linked_bids + block_idv_idr_bids:
                circular_pc_id = self._circular_pc_id.get(linked_order.name)
                if circular_pc_id is not None and circular_pc_id in dict_circular_children_bids:
                    circularly_linked_bids.extend(dict_circular_children_bids[circular_pc_id])
                    # This circular set has already been reassigned to a global linked set,
                    # we can delete it from the initial dictionary
                    del dict_circular_children_bids[circular_pc_id]

            # Add circular parent-child orders and block identical volume (idv)
            #     and identical ratio (idr) orders
            linked_bids.extend(circularly_linked_bids)
            linked_bids.extend(block_idv_idr_bids)

            order_names = list(dict.fromkeys(order.name for order in linked_bids))
            dict_linked_bids[index_lo] = [self._mc_orders[order_name] for order_name in order_names]
            index_lo += 1

        for mc_order_coupling in complement_coupling_list:
            list_order_direction = []
            for order in mc_order_coupling.orders:
                mc_order = self._mc_orders[order.name]
                if mc_order.is_sale:
                    list_order_direction.append(-1)
                else:
                    list_order_direction.append(1)
            order_direction = list(set(list_order_direction))

            if len(order_direction) > 1 or mc_order_coupling.complement_direction == ComplementDirection.EqualTo:
                dict_linked_bids[index_lo] = mc_order_coupling.orders
                index_lo += 1

            if len(order_direction) == 1:
                bool_is_buy = order_direction[0]
                if bool_is_buy * mc_order_coupling.complement_energy >= 0:
                    if bool_is_buy == -1 and mc_order_coupling.complement_direction == ComplementDirection.LesserThan:
                        dict_linked_bids[index_lo] = mc_order_coupling.orders
                        index_lo += 1
                    if bool_is_buy == 1 and mc_order_coupling.complement_direction == ComplementDirection.GreaterThan:
                        dict_linked_bids[index_lo] = mc_order_coupling.orders
                        index_lo += 1

        # Step 2 - Add the circular sets that have not yet been reassigned to a global LINK
        if len(dict_circular_children_bids) > 0:
            for index_pc_t in dict_circular_children_bids:
                dict_linked_bids[index_lo] = list(dict_circular_children_bids[index_pc_t])
                index_lo += 1

        # Step 3 - Instantiating full_link_id on concerned orders
        for index_lo, orders in dict_linked_bids.items():
            for order in orders:
                if order.name not in self._full_link_id:
                    self._full_link_id[order.name] = index_lo
        logger.debug("Dict linked bids before instantiating parent_child links : ")
        for key, values in dict_linked_bids.items():
            logger.debug(f"{key} : {values}")

        return dict_linked_bids

    # Defining global parent_child sets
    # Gets all the children from a parent set containing several parent orders
    def _get_children(self, parent_orders: list[Order]) -> list[Order]:
        list_children = []
        for order in parent_orders:
            mc_order = self._mc_orders[order.name]
            for mc_order_coupling in self._mc_order_couplings.values():
                if mc_order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                    market_area_name = self._mc_orders[mc_order_coupling.orders[0].name].market_area.name
                    if mc_order.market_area.name == market_area_name and order.name == mc_order_coupling.orders[0].name:
                        if mc_order_coupling.orders[1] not in parent_orders:
                            list_children.append(mc_order_coupling.orders[1])
        return list_children

    # Finds global parent_child links between orders (including the links between parents to merge them as a single
    # parent), defines the resulting sets and stores them in a dictionary
    def _compute_parent_child_sets(
        self, dict_linked_orders: dict[int, list[Order]]
    ) -> dict[int, tuple[list[Order], list[Order]]]:
        dict_parent_child_orders: dict[int, tuple[list[Order], list[Order]]] = {}
        index_pc = 0
        for mc_order_coupling in self._mc_order_couplings.values():
            if mc_order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                parent_order, child_order = mc_order_coupling.orders[:2]

                # Check if the parent is linked to other bids to consider them as parent as well
                full_link_id = self._full_link_id.get(parent_order.name)
                if full_link_id is not None:
                    if full_link_id in dict_linked_orders:
                        parent_link_orders = dict_linked_orders[full_link_id]
                        child_orders = self._get_children(parent_link_orders)
                        dict_parent_child_orders[index_pc] = (parent_link_orders, child_orders)
                        # The initial parent set is removed from global linked sets
                        # as it is now part of a global parent/child link
                        dict_linked_orders.pop(full_link_id)
                    else:
                        # One parent has already been browsed and enabled to gather all the parent orders into one set
                        continue
                else:
                    dict_parent_child_orders[index_pc] = ([parent_order], [child_order])
                index_pc += 1

        for index_pc, (parent_orders, children_orders) in dict_parent_child_orders.items():
            for order in parent_orders:
                if order.name not in self._full_pc_id:
                    self._full_pc_id[order.name] = index_pc
            id_child = 0
            for order in children_orders:
                if order.name not in self._full_pc_id:
                    self._full_pc_id[order.name] = index_pc
                if order.name not in self._child_id:
                    self._child_id[order.name] = str(id_child)
                    id_child += 1

        logger.debug(f"Final linked bids dict : {dict_linked_orders}")
        logger.debug(f"Final parent_child bids dict : {dict_parent_child_orders}")

        return dict_parent_child_orders
