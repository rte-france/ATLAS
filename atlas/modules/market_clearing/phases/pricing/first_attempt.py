"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

First pricing attempt: builds the LP that computes market-clearing prices under the standard
surplus/branch-load/price-difference constraints. If this attempt is infeasible, `second_attempt`
relaxes the rejected-orders surplus constraints, and `third_attempt` further relaxes paradoxically
accepted/rejected orders.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import pendulum

from atlas.config import logger
from atlas.modules.market_clearing.data_classes import PriceGroup
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.phases._helpers import (
    GroupPair,
    count_saturated,
    iter_group_pairs,
    times_by_group,
    times_by_group_pair,
)
from atlas.modules.market_clearing.phases.pricing._types import PricingVariables, RelaxableConstraints, _PricingPhase
from atlas.solver.temporal_variable import TemporalVariable

if TYPE_CHECKING:
    # ortools-stubs does not ship pywraplp (see the solver_interface mypy override)
    from ortools.linear_solver import pywraplp  # type: ignore[attr-defined]


def build_variables(pricing: _PricingPhase) -> PricingVariables:
    """Create all variables for the first pricing phase model

    :return: The temporal variables, which the later attempts build upon
    """
    with_slack = bool(pricing.parameters.fb_branch_load_slack_penalty)
    variables = PricingVariables(
        price=create_price_variables(pricing),
        positive_price=create_positive_price_variables(pricing),
        negative_price=create_negative_price_variables(pricing),
        positive_price_diff=create_positive_price_diff_variables(pricing),
        negative_price_diff=create_negative_price_diff_variables(pricing),
        positive_branch_load_slack=create_positive_branch_load_slack_variables(pricing) if with_slack else {},
        negative_branch_load_slack=create_negative_branch_load_slack_variables(pricing) if with_slack else {},
        shadow_price=create_shadow_price_variables(pricing),
        child_link_surplus=create_child_link_surplus_variables(pricing),
    )
    return variables


def build_constraints(pricing: _PricingPhase) -> RelaxableConstraints:
    """Create all constraints for the first pricing phase model

    :return: The names of the constraints that the later attempts may relax
    """
    if pricing.parameters.prevent_adverse_flows:
        create_adverse_flow_constraints(pricing)
    if pricing.parameters.market_price_penalty_beta:
        create_absolute_price_constraints(pricing)
    if not pricing.input_dataset.is_atc:
        create_branch_load_constraints(pricing)
    create_price_difference_constraints(pricing)
    create_shadow_price_constraints(pricing)
    return RelaxableConstraints(
        linked_orders_surplus=create_linked_orders_surplus_constraints(pricing),
        parent_child_surplus=create_parent_child_surplus_constraints(pricing),
        order_surplus=create_order_surplus_constraints(pricing),
        null_marginal_order=create_null_marginal_order_constraints(pricing),
    )


def build_objective(pricing: _PricingPhase) -> None:
    """Create objective function for the first pricing phase model"""
    pricing.model.set_direction("minimize")
    if pricing.parameters.market_price_penalty_alpha:
        create_price_objective(pricing)
    if pricing.parameters.market_price_penalty_beta:
        create_absolute_price_objective(pricing)
    if not pricing.input_dataset.is_atc and pricing.parameters.fb_branch_load_slack_penalty:
        create_branch_load_objective(pricing)
    create_price_difference_objective(pricing)


def instantiate_order_group_index(pricing: _PricingPhase) -> None:
    """Find the price group of a given order and fill its attribute"""
    for price_group_list in pricing.price_groups.values():
        for price_group in price_group_list:
            for market_area_name in price_group.market_area_names:
                for order in pricing.input_dataset.market_areas[market_area_name].orders.values():
                    if order.start_date == price_group.time:
                        order.group_index = price_group.id


##################################
# Variables
##################################
def create_child_link_surplus_variables(pricing: _PricingPhase) -> dict[str, pywraplp.Variable]:
    """Create the surplus each accepted child order gives to its parent-child group, keyed by child order name."""
    link_surplus = {}
    for index_pc, (_, child_orders) in pricing.parent_child_orders.items():
        accepted_children = [child_order for child_order in child_orders if pricing.is_accepted(child_order)]
        for index_child, child_order in enumerate(accepted_children):
            link_surplus[child_order.name] = pricing.model.add_continuous_variable(
                f"link_s_child_{index_child}_PC_{index_pc}", 0, float("inf")
            )
    return link_surplus


def create_price_variables(pricing: _PricingPhase) -> dict[int, TemporalVariable]:
    return {
        group_id: pricing.model.add_temporal_variable(f"price_on_group_{group_id}", times)
        for group_id, times in times_by_group(pricing.price_groups).items()
    }


def create_positive_price_variables(pricing: _PricingPhase) -> dict[int, TemporalVariable]:
    return {
        group_id: pricing.model.add_temporal_variable(f"positive_price_on_group_{group_id}", times, lower_bound=0.0)
        for group_id, times in times_by_group(pricing.price_groups).items()
    }


def create_negative_price_variables(pricing: _PricingPhase) -> dict[int, TemporalVariable]:
    return {
        group_id: pricing.model.add_temporal_variable(f"negative_price_on_group_{group_id}", times, upper_bound=0.0)
        for group_id, times in times_by_group(pricing.price_groups).items()
    }


def create_positive_price_diff_variables(pricing: _PricingPhase) -> dict[GroupPair, TemporalVariable]:
    return {
        (group_id, other_group_id): pricing.model.add_temporal_variable(
            f"positive_price_diff_of_groups_{group_id}_and_{other_group_id}", times, lower_bound=0.0
        )
        for (group_id, other_group_id), times in times_by_group_pair(pricing.price_groups).items()
    }


def create_negative_price_diff_variables(pricing: _PricingPhase) -> dict[GroupPair, TemporalVariable]:
    return {
        (group_id, other_group_id): pricing.model.add_temporal_variable(
            f"negative_price_diff_of_groups_{group_id}_and_{other_group_id}", times, upper_bound=0.0
        )
        for (group_id, other_group_id), times in times_by_group_pair(pricing.price_groups).items()
    }


def create_shadow_price_variables(pricing: _PricingPhase) -> dict[str, TemporalVariable]:
    return {
        critical_branch_name: pricing.model.add_temporal_variable(
            f"shadow_price_on_cb_{critical_branch_name}", pricing.input_dataset.times, upper_bound=0.0
        )
        for critical_branch_name in pricing.input_dataset.critical_branches
    }


def _unsaturated_price_groups(pricing: _PricingPhase) -> dict[pendulum.DateTime, list[PriceGroup]]:
    """Price groups of the time steps without any saturated critical branch, where branch loads get a slack."""
    return {
        time: price_groups
        for time, price_groups in pricing.price_groups.items()
        if count_saturated(pricing.saturated_critical_branch, time, pricing.parameters.allowed_round_off_error) == 0
    }


def create_positive_branch_load_slack_variables(pricing: _PricingPhase) -> dict[GroupPair, TemporalVariable]:
    return {
        (group_id, other_group_id): pricing.model.add_temporal_variable(
            f"Pos_slack_branch_load_btw_{group_id}_{other_group_id}", times, lower_bound=0.0
        )
        for (group_id, other_group_id), times in times_by_group_pair(_unsaturated_price_groups(pricing)).items()
    }


def create_negative_branch_load_slack_variables(pricing: _PricingPhase) -> dict[GroupPair, TemporalVariable]:
    return {
        (group_id, other_group_id): pricing.model.add_temporal_variable(
            f"Neg_slack_branch_load_btw_{group_id}_{other_group_id}", times, upper_bound=0.0
        )
        for (group_id, other_group_id), times in times_by_group_pair(_unsaturated_price_groups(pricing)).items()
    }


##################################
# Constraints
##################################
def _surplus(pricing: _PricingPhase, order: OrderMC) -> pywraplp.LinearExpr:
    """Surplus of an order at the price of its group, positive when the order gains from being accepted."""
    cleared_power = pricing.clearing_accepted_powers[order.market_area.name, order.name]
    return order.production_sign * cleared_power * (pricing.order_price(order) - order.price)


def _accepted_priced(pricing: _PricingPhase, orders: Iterable[OrderMC]) -> list[OrderMC]:
    """Keep the accepted orders that belong to a price group, the only ones with a surplus to constrain."""
    return [order for order in orders if order.group_index is not None and pricing.is_accepted(order)]


def create_linked_orders_surplus_constraints(pricing: _PricingPhase) -> list[str]:
    """Keep the overall surplus of each group of linked orders positive."""
    constraint_names = []
    for index_lo, orders in pricing.linked_orders.items():
        logger.debug(f"Surplus for : {index_lo}")
        surplus = sum(_surplus(pricing, order) for order in _accepted_priced(pricing, orders))
        constraint_name = f"positive_surplus_LO_{index_lo}"
        pricing.model.add_constraint(surplus >= 0.0, constraint_name)
        constraint_names.append(constraint_name)
    return constraint_names


def create_parent_child_surplus_constraints(pricing: _PricingPhase) -> list[str]:
    """Keep positive the surplus of each accepted child order net of what it gives to its group, and the
    surplus of the parent orders once given what their children give."""
    constraint_names = []
    for index_pc, (parent_orders, child_orders) in pricing.parent_child_orders.items():
        logger.debug(f"Surplus for PC {index_pc}")
        accepted_children = _accepted_priced(pricing, child_orders)
        for index_child, child_order in enumerate(accepted_children):
            constraint_name = f"pos_surplus_child_{index_child}_PC_{index_pc}_t_{child_order.start_date}"
            link_surplus = pricing.variables.child_link_surplus[child_order.name]
            pricing.model.add_constraint(_surplus(pricing, child_order) - link_surplus >= 0.0, constraint_name)
            constraint_names.append(constraint_name)

        surplus = sum(_surplus(pricing, parent_order) for parent_order in _accepted_priced(pricing, parent_orders))
        if surplus:
            children_link_surplus = sum(
                pricing.variables.child_link_surplus[child_order.name] for child_order in accepted_children
            )
            constraint_name = f"neg_surplus_parent_PC_{index_pc}"
            pricing.model.add_constraint(surplus + children_link_surplus >= 0.0, constraint_name)
            constraint_names.append(constraint_name)
    return constraint_names


def create_order_surplus_constraints(pricing: _PricingPhase) -> list[str]:
    """Keep the surplus of each accepted standalone order positive."""
    constraint_names = []
    for order in _accepted_priced(pricing, pricing.standalone_orders()):
        equipment_name = order.equipment.name if order.equipment else "NA"
        constraint_name = (
            f"pos_surplus_order_{order.name}_area_{order.market_area.name}_eqpt_{equipment_name}_t_{order.start_date}"
        )
        pricing.model.add_constraint(_surplus(pricing, order) >= 0.0, constraint_name)
        constraint_names.append(constraint_name)
    return constraint_names


def create_null_marginal_order_constraints(pricing: _PricingPhase) -> list[str]:
    """Cancel the surplus of each standalone order accepted strictly between its minimum and maximum power."""
    tolerance = pricing.parameters.allowed_round_off_error
    constraint_names = []
    for order in _accepted_priced(pricing, pricing.standalone_orders()):
        cleared_power = pricing.clearing_accepted_powers[order.market_area.name, order.name]
        is_marginal = abs(cleared_power - order.qmin) >= tolerance and abs(cleared_power - order.qmax) >= tolerance
        if order.is_linked or not is_marginal:
            continue
        equipment_name = order.equipment.name if order.equipment else "NA"
        constraint_name = f"s_null_marginal_order_{order.name}_area_{order.market_area.name}_eqpt_{equipment_name}_t_{order.start_date}"
        pricing.model.add_constraint(_surplus(pricing, order) == 0.0, constraint_name)
        constraint_names.append(constraint_name)
    return constraint_names


def create_shadow_price_constraints(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        for critical_branch_name in pricing.input_dataset.critical_branches:
            shadow_price = pricing.variables.shadow_price[critical_branch_name][time]
            saturated_critical_branch = pricing.saturated_critical_branch[critical_branch_name, time]
            if saturated_critical_branch > pricing.parameters.allowed_round_off_error:
                pricing.model.add_constraint(
                    saturated_critical_branch * shadow_price == 0.0,
                    f"Complementarity_shadow_price_t_{time}_cb_{critical_branch_name}",
                )


def create_adverse_flow_constraints(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        for border_name, border in pricing.input_dataset.market_borders.items():
            border_exchange = pricing.clearing_border_exchanges[border_name, time]
            if abs(border_exchange) < pricing.parameters.allowed_round_off_error:
                continue
            price_in, price_out = None, None
            for price_group in pricing.price_groups[time]:
                if border.uphill_market_area.name in price_group.market_area_names:
                    price_in = pricing.variables.price[price_group.id][time]
                if border.downhill_market_area.name in price_group.market_area_names:
                    price_out = pricing.variables.price[price_group.id][time]

            if price_in and not price_out:
                pricing.model.add_constraint(
                    -border_exchange * price_in >= 0.0,
                    f"prevent_adv_flow_on_{border_name}_at_{time}",
                )
            elif price_out and not price_in:
                pricing.model.add_constraint(
                    border_exchange * price_out >= 0.0,
                    f"prevent_adv_flow_on_{border_name}_at_{time}",
                )


def create_absolute_price_constraints(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        for price_group in pricing.price_groups[time]:
            positive_price = pricing.variables.positive_price[price_group.id][time]
            negative_price = pricing.variables.negative_price[price_group.id][time]
            price = pricing.variables.price[price_group.id][time]
            pricing.model.add_constraint(
                positive_price + negative_price - price == 0.0,
                f"Price_pos_neg_group_{price_group.id}_t_{time}",
            )


def create_branch_load_constraints(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        price_groups = pricing.price_groups[time]
        if count_saturated(pricing.saturated_critical_branch, time, pricing.parameters.allowed_round_off_error) != 0:
            continue
        for group_i, group_j in iter_group_pairs(price_groups):
            price = pricing.variables.price[group_i.id][time]
            other_price = pricing.variables.price[group_j.id][time]
            branch_load = price - other_price
            if pricing.parameters.fb_branch_load_slack_penalty:
                positive_slack = pricing.variables.positive_branch_load_slack[(group_i.id, group_j.id)][time]
                negative_slack = pricing.variables.negative_branch_load_slack[(group_i.id, group_j.id)][time]
                branch_load += positive_slack + negative_slack
            for critical_branch_name, _ in pricing.input_dataset.critical_branches.items():
                for market_area_name in pricing.input_dataset.market_areas:
                    if market_area_name in group_i.market_area_names:
                        coeff = 1.0
                    elif market_area_name in group_j.market_area_names:
                        coeff = -1.0
                    else:
                        continue

                    if market_area_name in pricing.input_dataset.market_area_ptdfs:
                        mc_market_area_ptdf = pricing.input_dataset.market_area_ptdfs[market_area_name]
                        shadow_prices_fb = pricing.variables.shadow_price[critical_branch_name][time]
                        branch_load += coeff * mc_market_area_ptdf.day_ahead_ptdf.get_value(time) * shadow_prices_fb

            pricing.model.add_constraint(
                branch_load == 0.0,
                f"price_ptdf_time_{time}_areas_{group_i.id}-{group_j.id}",
            )


def create_price_difference_constraints(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        price_groups = pricing.price_groups[time]
        for group_i, group_j in iter_group_pairs(price_groups):
            if not pricing.is_neighbour(group_i, group_j):
                continue
            price = pricing.variables.price[group_i.id][time]
            other_price = pricing.variables.price[group_j.id][time]
            positive_price_diff = pricing.variables.positive_price_diff[(group_i.id, group_j.id)][time]
            negative_price_diff = pricing.variables.negative_price_diff[(group_i.id, group_j.id)][time]

            pricing.model.add_constraint(
                positive_price_diff + negative_price_diff == price - other_price,
                f"def_price_diff_groups_{group_i.id}_and_{group_j.id}_at_{time}",
            )


def create_price_objective(pricing: _PricingPhase) -> None:
    objective = []
    for time in pricing.input_dataset.times:
        for price_group in pricing.price_groups[time]:
            price = pricing.variables.price[price_group.id][time]
            objective.append(pricing.parameters.market_price_penalty_alpha * price)
    pricing.model.add_objective(sum(objective))


def create_absolute_price_objective(pricing: _PricingPhase) -> None:
    objective = []
    for time in pricing.input_dataset.times:
        for price_group in pricing.price_groups[time]:
            positive_price = pricing.variables.positive_price[price_group.id][time]
            negative_price = pricing.variables.negative_price[price_group.id][time]
            objective.append(pricing.parameters.market_price_penalty_beta * (positive_price - negative_price))
    pricing.model.add_objective(sum(objective))


def create_branch_load_objective(pricing: _PricingPhase) -> None:
    objective = []
    for time in pricing.input_dataset.times:
        if count_saturated(pricing.saturated_critical_branch, time, pricing.parameters.allowed_round_off_error) != 0:
            continue
        price_groups = pricing.price_groups[time]
        for group_i, group_j in iter_group_pairs(price_groups):
            positive_load_slack = pricing.variables.positive_branch_load_slack[(group_i.id, group_j.id)][time]
            negative_load_slack = pricing.variables.negative_branch_load_slack[(group_i.id, group_j.id)][time]
            objective.append(
                pricing.parameters.fb_branch_load_slack_penalty * (positive_load_slack - negative_load_slack)
            )
    pricing.model.add_objective(sum(objective))


def create_price_difference_objective(pricing: _PricingPhase) -> None:
    objective = []
    for time in pricing.input_dataset.times:
        price_groups = pricing.price_groups[time]
        for group_i, group_j in iter_group_pairs(price_groups):
            if not pricing.is_neighbour(group_i, group_j):
                continue
            positive_price_diff = pricing.variables.positive_price_diff[(group_i.id, group_j.id)][time]
            negative_price_diff = pricing.variables.negative_price_diff[(group_i.id, group_j.id)][time]
            objective.append(
                pricing.parameters.fb_branch_load_slack_penalty * (positive_price_diff - negative_price_diff)
            )
    pricing.model.add_objective(sum(objective))
