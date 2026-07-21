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

from atlas.config import logger
from atlas.enums import ComplementDirection, CouplingType
from atlas.modules.market_clearing.data_classes import IdvIdrCouplingIndex, OrderLinks
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.input_objects.order_coupling import OrderCouplingMC
from atlas.objects.market.order import Order


class OrderLinkResolver:
    """Resolves the order couplings of a market_clearing dataset into linked/parent-child sets."""

    def __init__(self, orders: dict[str, OrderMC], order_couplings: dict[str, OrderCouplingMC]):
        self._orders = orders
        self._order_couplings = order_couplings
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
        for order_coupling in self._order_couplings.values():
            if order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                list_children = [order_coupling.orders[0]]
                circular_orders = self._get_circular_children(order_coupling, list_children, [])
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
        self, order_coupling: OrderCouplingMC, orders: list[Order], processed_order_couplings: list[str]
    ) -> list[Order]:
        parent_order, child_order = order_coupling.orders[:2]
        child_mc_order = self._orders[child_order.name]
        processed_order_couplings.append(order_coupling.name)
        order_coupling_parent_ids = child_mc_order.order_coupling_parent_ids

        # A parent/child link is considered transitive when the child is also a parent elsewhere
        if child_mc_order.is_parent and order_coupling_parent_ids:
            orders.append(child_order)
            for order_coupling_name in order_coupling_parent_ids:
                if order_coupling_name not in processed_order_couplings:
                    self._get_circular_children(order_coupling, orders, processed_order_couplings)
            return orders
        # The child is not a parent, the transitive parent/child link stops here
        return orders

    # Finds global links between orders (including circular parent_child links), defines the resulting sets and stores
    # them in a dictionary
    def _compute_linked_bids_sets(self, dict_circular_children_bids: dict[int, list[Order]]) -> dict[int, list[Order]]:
        dict_linked_bids: dict[int, list[Order]] = {}
        next_index = 0

        complement_couplings, idv_idr_index = self._partition_couplings_for_linking()

        treated_order_couplings: list[str] = []
        for order_coupling_name in idv_idr_index.orders_by_coupling:
            # Check if we have already treated this order coupling (could be the case in an idv/idr block)
            if order_coupling_name in treated_order_couplings:
                continue
            treated_order_couplings.append(order_coupling_name)
            dict_linked_bids[next_index] = self._resolve_idv_idr_linked_group(
                order_coupling_name,
                next_index,
                idv_idr_index,
                dict_circular_children_bids,
                treated_order_couplings,
            )
            next_index += 1

        for orders in self._resolve_complement_linked_groups(complement_couplings):
            dict_linked_bids[next_index] = orders
            next_index += 1

        # Any circular parent-child set not folded into a link above stands as its own linked group
        for orders in dict_circular_children_bids.values():
            dict_linked_bids[next_index] = list(orders)
            next_index += 1

        self._assign_full_link_ids(dict_linked_bids)

        logger.debug("Dict linked bids before instantiating parent_child links : ")
        for key, values in dict_linked_bids.items():
            logger.debug(f"{key} : {values}")

        return dict_linked_bids

    def _partition_couplings_for_linking(
        self,
    ) -> tuple[list[OrderCouplingMC], IdvIdrCouplingIndex]:
        """Split order couplings into COMPLEMENT (handled separately) and
        IDENTICAL_VOLUME/IDENTICAL_RATIO, indexing the latter both by coupling name and, for each
        order, by every IDV/IDR coupling it's part of.
        """
        complement_couplings = []
        orders_by_coupling: dict[str, list[str]] = {}
        couplings_by_order: dict[str, list[str]] = {}
        for order_coupling in self._order_couplings.values():
            if order_coupling.coupling_type == CouplingType.COMPLEMENT:
                complement_couplings.append(order_coupling)
                continue
            if order_coupling.coupling_type not in (CouplingType.IDENTICAL_VOLUME, CouplingType.IDENTICAL_RATIO):
                continue

            orders_by_coupling[order_coupling.name] = []
            for order in order_coupling.orders:
                orders_by_coupling[order_coupling.name].append(order.name)
                couplings_by_order.setdefault(order.name, []).append(order_coupling.name)

        return complement_couplings, IdvIdrCouplingIndex(orders_by_coupling, couplings_by_order)

    def _resolve_idv_idr_linked_group(
        self,
        order_coupling_name: str,
        index_lo: int,
        idv_idr_index: IdvIdrCouplingIndex,
        dict_circular_children_bids: dict[int, list[Order]],
        treated_order_couplings: list[str],
    ) -> list[Order]:
        """Resolve one IDENTICAL_VOLUME/IDENTICAL_RATIO coupling into its full linked group: every
        order transitively linked through shared IDV/IDR couplings, plus any circular
        parent-child set one of those orders belongs to.
        """
        order_coupling = self._order_couplings[order_coupling_name]
        linked_bids = order_coupling.orders
        block_idv_idr_bids = self._get_idv_idr_block_sets(
            order_coupling,
            [],
            treated_order_couplings,
            index_lo,
            idv_idr_index,
        )

        circularly_linked_bids = []
        for linked_order in linked_bids + block_idv_idr_bids:
            circular_pc_id = self._circular_pc_id.get(linked_order.name)
            if circular_pc_id is not None and circular_pc_id in dict_circular_children_bids:
                circularly_linked_bids.extend(dict_circular_children_bids[circular_pc_id])
                # This circular set has already been reassigned to a global linked set,
                # we can delete it from the initial dictionary
                del dict_circular_children_bids[circular_pc_id]

        # Add circular parent-child orders and block identical volume (idv) and identical ratio (idr) orders
        linked_bids.extend(circularly_linked_bids)
        linked_bids.extend(block_idv_idr_bids)

        order_names = list(dict.fromkeys(order.name for order in linked_bids))
        return [self._orders[order_name] for order_name in order_names]

    # Recursively gathers every order transitively linked through shared IDV/IDR couplings
    def _get_idv_idr_block_sets(
        self,
        order_coupling: OrderCouplingMC,
        block_idv_idr_bids: list[OrderMC],
        treated_order_couplings: list[str],
        index_lo: int,
        idv_idr_index: IdvIdrCouplingIndex,
    ) -> list[OrderMC]:
        for order_name in idv_idr_index.orders_by_coupling[order_coupling.name]:
            order = self._orders[order_name]
            block_idv_idr_bids.append(order)
            self._full_link_id[order_name] = index_lo

            for linked_order_coupling_name in idv_idr_index.couplings_by_order.get(order_name, []):
                if linked_order_coupling_name in treated_order_couplings:
                    continue
                treated_order_couplings.append(linked_order_coupling_name)
                linked_order_coupling = self._order_couplings[linked_order_coupling_name]
                self._get_idv_idr_block_sets(
                    linked_order_coupling,
                    block_idv_idr_bids,
                    treated_order_couplings,
                    index_lo,
                    idv_idr_index,
                )

        return block_idv_idr_bids

    def _resolve_complement_linked_groups(self, complement_couplings: list[OrderCouplingMC]) -> list[list[Order]]:
        """Resolve COMPLEMENT couplings into linked groups.

        Note the two conditions below are independent (not if/elif): when the coupling's orders
        all trade the same direction *and* its complement_direction is EqualTo, both can fire,
        producing two groups for the same coupling. That mirrors the original behaviour exactly.
        """
        groups = []
        for order_coupling in complement_couplings:
            directions = {(-1 if self._orders[order.name].is_sale else 1) for order in order_coupling.orders}

            if len(directions) > 1 or order_coupling.complement_direction == ComplementDirection.EqualTo:
                groups.append(order_coupling.orders)

            if len(directions) == 1:
                (direction,) = directions
                if direction * order_coupling.complement_energy >= 0:
                    if direction == -1 and order_coupling.complement_direction == ComplementDirection.LesserThan:
                        groups.append(order_coupling.orders)
                    if direction == 1 and order_coupling.complement_direction == ComplementDirection.GreaterThan:
                        groups.append(order_coupling.orders)

        return groups

    def _assign_full_link_ids(self, dict_linked_bids: dict[int, list[Order]]) -> None:
        for index_lo, orders in dict_linked_bids.items():
            for order in orders:
                if order.name not in self._full_link_id:
                    self._full_link_id[order.name] = index_lo

    # Defining global parent_child sets
    # Gets all the children from a parent set containing several parent orders
    def _get_children(self, parent_orders: list[Order]) -> list[Order]:
        list_children = []
        for order in parent_orders:
            order = self._orders[order.name]
            for order_coupling in self._order_couplings.values():
                if order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                    market_area_name = self._orders[order_coupling.orders[0].name].market_area.name
                    if order.market_area.name == market_area_name and order.name == order_coupling.orders[0].name:
                        if order_coupling.orders[1] not in parent_orders:
                            list_children.append(order_coupling.orders[1])
        return list_children

    # Finds global parent_child links between orders (including the links between parents to merge them as a single
    # parent), defines the resulting sets and stores them in a dictionary
    def _compute_parent_child_sets(
        self, dict_linked_orders: dict[int, list[Order]]
    ) -> dict[int, tuple[list[Order], list[Order]]]:
        dict_parent_child_orders = self._group_parent_child_couplings(dict_linked_orders)
        self._assign_full_pc_and_child_ids(dict_parent_child_orders)

        logger.debug(f"Final linked bids dict : {dict_linked_orders}")
        logger.debug(f"Final parent_child bids dict : {dict_parent_child_orders}")

        return dict_parent_child_orders

    def _group_parent_child_couplings(
        self, dict_linked_orders: dict[int, list[Order]]
    ) -> dict[int, tuple[list[Order], list[Order]]]:
        """Group PARENT_CHILDREN couplings into parent/children sets, merging a parent's whole
        linked-order group into the parent set when the parent itself is IDV/IDR-linked.
        """
        dict_parent_child_orders: dict[int, tuple[list[Order], list[Order]]] = {}
        index_pc = 0
        for order_coupling in self._order_couplings.values():
            if order_coupling.coupling_type != CouplingType.PARENT_CHILDREN:
                continue
            parent_order, child_order = order_coupling.orders[:2]

            # Check if the parent is linked to other bids to consider them as parent as well
            full_link_id = self._full_link_id.get(parent_order.name)
            if full_link_id is None:
                dict_parent_child_orders[index_pc] = ([parent_order], [child_order])
            elif full_link_id in dict_linked_orders:
                parent_link_orders = dict_linked_orders[full_link_id]
                child_orders = self._get_children(parent_link_orders)
                dict_parent_child_orders[index_pc] = (parent_link_orders, child_orders)
                # The initial parent set is removed from global linked sets
                # as it is now part of a global parent/child link
                dict_linked_orders.pop(full_link_id)
            else:
                # One parent has already been browsed and enabled to gather all the parent orders into one set
                continue
            index_pc += 1

        return dict_parent_child_orders

    def _assign_full_pc_and_child_ids(
        self, dict_parent_child_orders: dict[int, tuple[list[Order], list[Order]]]
    ) -> None:
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
