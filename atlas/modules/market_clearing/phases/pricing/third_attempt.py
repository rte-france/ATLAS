"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Third pricing attempt: run when the second attempt is still infeasible. Deactivates the remaining
positive-surplus constraints and instead penalizes any paradoxically accepted/rejected order by
its opposite delta-P (the gap between its own price and the clearing price it actually got).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.modules.market_clearing.constants as constants
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.phases.pricing._types import ParadoxVariables, _PricingPhase

if TYPE_CHECKING:
    # ortools-stubs does not ship pywraplp (see the solver_interface mypy override)
    from ortools.linear_solver import pywraplp  # type: ignore[attr-defined]


def build_variables(pricing: _PricingPhase, opposite_delta_p_dict: dict[int, float | None]) -> ParadoxVariables:
    """Create all variables for the third pricing phase model"""
    return ParadoxVariables(
        linked_orders=create_linked_orders_delta_p_variables(pricing),
        parent_child=create_parent_child_delta_p_variables(pricing, opposite_delta_p_dict),
        orders=create_order_delta_p_variables(pricing),
    )


def build_constraints(
    pricing: _PricingPhase, paradox: ParadoxVariables, opposite_delta_p_dict: dict[int, float | None]
) -> None:
    """Create all constraints for the third pricing phase model"""
    relax_surplus_constraints(pricing)
    create_linked_orders_delta_p_constraints(pricing, paradox)
    create_parent_child_delta_p_constraints(pricing, paradox, opposite_delta_p_dict)
    create_order_delta_p_constraints(pricing, paradox)


def build_objective(pricing: _PricingPhase, paradox: ParadoxVariables) -> None:
    """Create objective function for the third pricing phase model: penalize every paradoxical delta-P"""
    delta_p = [*paradox.linked_orders.values(), *paradox.parent_child.values(), *paradox.orders.values()]
    pricing.model.add_objective(pricing.parameters.paradoxically_accepted_penalty * sum(delta_p))


def compute_opposite_delta_p(pricing: _PricingPhase) -> dict[int, float | None]:
    """Sum the opposite delta-P of the accepted orders of each parent-child group, None if none is accepted."""
    opposite_delta_p_dict: dict[int, float | None] = {}
    for index_pc, (parent_orders, children_orders) in pricing.parent_child_orders.items():
        opposite_delta_p = None
        for order in parent_orders + children_orders:
            if order.group_index is None or not pricing.is_accepted(order):
                continue
            delta = _opposite_delta_p(pricing, order)
            opposite_delta_p = delta if opposite_delta_p is None else opposite_delta_p + delta
        opposite_delta_p_dict[index_pc] = opposite_delta_p
    return opposite_delta_p_dict


def _opposite_delta_p(pricing: _PricingPhase, order: OrderMC) -> pywraplp.LinearExpr:
    """Gap between the price of an order and the price of its group, positive when the order is paradoxical."""
    return order.production_sign * (order.price - pricing.order_price(order))


def create_linked_orders_delta_p_variables(pricing: _PricingPhase) -> dict[int, pywraplp.Variable]:
    return {
        index_lo: pricing.model.add_continuous_variable(f"delta_p_LO_{index_lo}", 0, float("inf"))
        for index_lo in pricing.linked_orders
    }


def create_parent_child_delta_p_variables(
    pricing: _PricingPhase, opposite_delta_p_dict: dict[int, float | None]
) -> dict[int, pywraplp.Variable]:
    return {
        index_pc: pricing.model.add_continuous_variable(constants.delta_p_pc(index_pc), 0, float("inf"))
        for index_pc in pricing.parent_child_orders
        if opposite_delta_p_dict[index_pc] is not None
    }


def create_order_delta_p_variables(pricing: _PricingPhase) -> dict[str, pywraplp.Variable]:
    delta_p = {}
    for order in pricing.standalone_orders():
        if order.requires_status_variable is None or order.parent_child_id is not None:
            continue
        if pricing.is_accepted(order):
            delta_p[order.name] = pricing.model.add_continuous_variable(
                f"delta_p_order_{order.name}_area_{order.market_area.name}_t_{order.start_date}", 0, float("inf")
            )
    return delta_p


def relax_surplus_constraints(pricing: _PricingPhase) -> None:
    """Relax the positive surplus of the linked orders, the parent-child groups and the accepted orders,
    which the paradoxical delta-P penalties replace."""
    relaxable = pricing.relaxable
    for constraint_name in relaxable.linked_orders_surplus + relaxable.parent_child_surplus + relaxable.order_surplus:
        pricing.model.deactivate_constraint(constraint_name)


def create_order_delta_p_constraints(pricing: _PricingPhase, paradox: ParadoxVariables) -> None:
    for order in pricing.standalone_orders():
        if order.requires_status_variable is not None and order.parent_child_id is None:
            if pricing.is_accepted(order) and order.group_index is not None:
                pricing.model.add_constraint(
                    paradox.orders[order.name] >= _opposite_delta_p(pricing, order),
                    f"paradoxical_delta_p_order_{order.name}_area_{order.market_area.name}_t_{order.start_date}",
                )


def create_parent_child_delta_p_constraints(
    pricing: _PricingPhase, paradox: ParadoxVariables, opposite_delta_p_dict: dict[int, float | None]
) -> None:
    for index_pc, delta_p in paradox.parent_child.items():
        pricing.model.add_constraint(
            delta_p >= opposite_delta_p_dict[index_pc],
            f"paradoxical_delta_p_PC_{index_pc}",
        )


def create_linked_orders_delta_p_constraints(pricing: _PricingPhase, paradox: ParadoxVariables) -> None:
    for index_lo, orders in pricing.linked_orders.items():
        opposite_delta_p = sum(
            _opposite_delta_p(pricing, order)
            for order in orders
            if order.group_index is not None and pricing.is_accepted(order)
        )
        pricing.model.add_constraint(
            paradox.linked_orders[index_lo] >= opposite_delta_p,
            f"paradoxical_delta_p_LO_{index_lo}",
        )
