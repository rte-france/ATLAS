"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

First pricing attempt: builds the LP that computes market-clearing prices under the standard
surplus/branch-load/price-difference constraints. If this attempt is infeasible, `second_attempt`
relaxes the rejected-orders surplus constraints, and `third_attempt` further relaxes paradoxically
accepted/rejected orders.
"""

import atlas.modules.market_clearing.constants as constants
from atlas.config import logger
from atlas.modules.market_clearing.phases._helpers import count_saturated, iter_group_pairs
from atlas.modules.market_clearing.phases.pricing._types import _PricingPhase


def build_variables(pricing: _PricingPhase) -> None:
    """Create all variables for the first pricing phase model"""
    create_price_variables(pricing)
    create_positive_price_variables(pricing)
    create_negative_price_variables(pricing)
    create_positive_diff_price_variables(pricing)
    create_negative_diff_price_variables(pricing)
    if pricing.parameters.fb_branch_load_slack_penalty:
        create_positive_slack_branch_load_variables(pricing)
        create_negative_slack_branch_load_variables(pricing)
    create_shadow_price_variables(pricing)
    create_link_child_to_pc_variables(pricing)


def build_constraints(pricing: _PricingPhase) -> None:
    """Create all constraints for the first pricing phase model"""
    if pricing.parameters.prevent_adverse_flows:
        create_adverse_flow_constraint(pricing)
    if pricing.parameters.market_price_penalty_beta:
        create_absolute_price_group_constraint(pricing)
    if not pricing.input_dataset.is_atc:
        create_branch_load_constraint(pricing)
    create_add_price_difference_constraint(pricing)
    create_shadow_price_constraints(pricing)
    create_linked_bid_surplus_constraints(pricing)
    create_parent_child_surplus_constraints(pricing)
    create_pos_surplus_order_constraints(pricing)
    create_null_marginal_order_constraints(pricing)


def build_objective(pricing: _PricingPhase) -> None:
    """Create objective function for the first pricing phase model"""
    pricing.model.set_direction("minimize")
    if pricing.parameters.market_price_penalty_alpha:
        create_groups_prices_objective(pricing)
    if pricing.parameters.market_price_penalty_beta:
        create_absolute_price_objective(pricing)
    if not pricing.input_dataset.is_atc and pricing.parameters.fb_branch_load_slack_penalty:
        create_branch_load_objective(pricing)
    create_groups_price_diff_objective(pricing)


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
def create_link_child_to_pc_variables(pricing: _PricingPhase) -> None:
    for index_pc, (_, child_orders) in pricing.dict_parent_child_orders.items():
        index_child = 0
        for child_order in child_orders:
            local_cleared_power = pricing.clearing_accepted_powers[child_order.market_area.name, child_order.name]
            if local_cleared_power > pricing.parameters.allowed_round_off_error:
                pricing.model.add_continuous_variable(
                    constants.link_child_to_pc(index_child, index_pc), 0, float("inf")
                )
                index_child += 1


def create_price_variables(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        for price_group in pricing.price_groups[time]:
            pricing.model.add_continuous_variable(
                constants.price_on_group_variable_name(price_group.id, time),
                -float("inf"),
                float("inf"),
            )


def create_positive_price_variables(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        for price_group in pricing.price_groups[time]:
            pricing.model.add_continuous_variable(
                constants.positive_price_on_group_variable_name(price_group.id, time),
                0.0,
                float("inf"),
            )


def create_negative_price_variables(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        for price_group in pricing.price_groups[time]:
            pricing.model.add_continuous_variable(
                constants.negative_price_on_group_variable_name(price_group.id, time),
                -float("inf"),
                0.0,
            )


def create_positive_diff_price_variables(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        price_groups = pricing.price_groups[time]
        for group_i, group_j in iter_group_pairs(price_groups):
            pricing.model.add_continuous_variable(
                constants.positive_price_diff_on_group_variable_name(group_i.id, group_j.id, time),
                0.0,
                float("inf"),
            )


def create_negative_diff_price_variables(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        price_groups = pricing.price_groups[time]
        for group_i, group_j in iter_group_pairs(price_groups):
            pricing.model.add_continuous_variable(
                constants.negative_price_diff_on_group_variable_name(group_i.id, group_j.id, time),
                -float("inf"),
                0.0,
            )


def create_shadow_price_variables(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        for critical_branch_name in pricing.input_dataset.critical_branches:
            pricing.model.add_continuous_variable(
                constants.shadow_price_variable_name(critical_branch_name, time),
                -float("inf"),
                0.0,
            )


def create_positive_slack_branch_load_variables(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        price_groups = pricing.price_groups[time]
        if count_saturated(pricing.saturated_critical_branch, time, pricing.parameters.allowed_round_off_error) != 0:
            continue
        for group_i, group_j in iter_group_pairs(price_groups):
            pricing.model.add_continuous_variable(
                constants.positive_slack_branch_load_variable_name(group_i.id, group_j.id, time),
                0.0,
                float("inf"),
            )


def create_negative_slack_branch_load_variables(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        price_groups = pricing.price_groups[time]
        if count_saturated(pricing.saturated_critical_branch, time, pricing.parameters.allowed_round_off_error) != 0:
            continue
        for group_i, group_j in iter_group_pairs(price_groups):
            pricing.model.add_continuous_variable(
                constants.negative_slack_branch_load_variable_name(group_i.id, group_j.id, time),
                -float("inf"),
                0.0,
            )


##################################
# Constraints
##################################
def create_linked_bid_surplus_constraints(pricing: _PricingPhase) -> None:
    for index_lo, orders in pricing.dict_linked_orders.items():
        logger.debug(f"Surplus for : {index_lo}")
        surplus = 0
        for order in orders:
            if order.group_index is None:
                continue
            local_price = pricing.model.get_variable(
                constants.price_on_group_variable_name(order.group_index, order.start_date)
            )
            local_cleared_power = pricing.clearing_accepted_powers[order.market_area.name, order.name]
            coeff_sale = order.production_sign

            # If order is accepted, add its surplus to the overall surplus of this group of linked orders
            if local_cleared_power > pricing.parameters.allowed_round_off_error:
                surplus += coeff_sale * local_cleared_power * (local_price - order.price)

        pricing.model.add_constraint(
            surplus >= 0.0,
            constants.linked_bids_surplus_constraint_name(index_lo),
        )


# Global parent_child bids' surplus
def create_parent_child_surplus_constraints(pricing: _PricingPhase) -> None:
    for index_pc, (parent_orders, child_orders) in pricing.dict_parent_child_orders.items():
        index_child = 0
        logger.debug(f"Surplus for PC {index_pc}")

        sum_children_link_surplus = 0

        # Setting constraints individually for child orders
        for child_order in child_orders:
            if child_order.group_index is None:
                continue

            local_price = pricing.model.get_variable(
                constants.price_on_group_variable_name(child_order.group_index, child_order.start_date)
            )
            local_cleared_power = pricing.clearing_accepted_powers[child_order.market_area.name, child_order.name]
            coeff_sale = child_order.production_sign

            if local_cleared_power > pricing.parameters.allowed_round_off_error:
                link_surplus = pricing.model.get_variable(constants.link_child_to_pc(index_child, index_pc))
                sum_children_link_surplus += link_surplus
                logger.debug(f"surplus child {index_child} PC {index_pc}")
                pricing.model.add_constraint(
                    (coeff_sale * local_cleared_power * (local_price - child_order.price) - link_surplus) >= 0.0,
                    constants.positive_parent_child_surplus_constraint_name(
                        index_child, index_pc, child_order.start_date
                    ),
                )
                index_child += 1

        # Then set global constraint on parents
        surplus = 0
        for parent_order in parent_orders:
            if parent_order.group_index is None:
                continue

            local_price = pricing.model.get_variable(
                constants.price_on_group_variable_name(parent_order.group_index, parent_order.start_date)
            )
            local_cleared_power = pricing.clearing_accepted_powers[parent_order.market_area.name, parent_order.name]
            coeff_sale = parent_order.production_sign

            # If order is accepted, add its surplus to the overall surplus of this group of linked orders
            if local_cleared_power > pricing.parameters.allowed_round_off_error:
                surplus += coeff_sale * local_cleared_power * (local_price - parent_order.price)
        logger.debug(f"Surplus parent PC {index_pc}")
        if surplus:
            pricing.model.add_constraint(
                surplus + sum_children_link_surplus >= 0.0,
                constants.negative_parent_child_surplus_constraint_name(index_pc),
            )


def create_pos_surplus_order_constraints(pricing: _PricingPhase) -> None:
    for order in pricing.input_dataset.orders.values():
        if order.name not in pricing._full_link_id_by_order and order.parent_child_id is None:
            if order.group_index is None:
                continue

            local_price = pricing.model.get_variable(
                constants.price_on_group_variable_name(order.group_index, order.start_date)
            )
            local_cleared_power = pricing.clearing_accepted_powers[order.market_area.name, order.name]

            if local_cleared_power > pricing.parameters.allowed_round_off_error:
                coeff_sale = order.production_sign
                equipment_name = order.equipment.name if order.equipment else "NA"
                pricing.model.add_constraint(
                    coeff_sale * local_cleared_power * (local_price - order.price) >= 0.0,
                    constants.pos_surplus_order_constraint_name(
                        order.name, equipment_name, order.market_area.name, order.start_date
                    ),
                )


def create_null_marginal_order_constraints(pricing: _PricingPhase) -> None:
    for order in pricing.input_dataset.orders.values():
        if order.name not in pricing._full_link_id_by_order and order.parent_child_id is None:
            if order.group_index is None:
                continue

            local_price = pricing.model.get_variable(
                constants.price_on_group_variable_name(order.group_index, order.start_date)
            )
            local_cleared_power = pricing.clearing_accepted_powers[order.market_area.name, order.name]

            if local_cleared_power > pricing.parameters.allowed_round_off_error:
                coeff_sale = order.production_sign
                equipment_name = order.equipment.name if order.equipment else "NA"
                # MARGINAL SURPLUS: if the bid is not linked and marginally accepted, its surplus should be null
                if not order.is_linked:
                    if (
                        abs(local_cleared_power - order.qmin) >= pricing.parameters.allowed_round_off_error
                        and abs(local_cleared_power - order.qmax) >= pricing.parameters.allowed_round_off_error
                    ):
                        constraint_name = constants.null_marginal_order_constraint_name(
                            order.name, equipment_name, order.market_area.name, order.start_date
                        )
                        pricing.model.add_constraint(
                            coeff_sale * local_cleared_power * (local_price - order.price) == 0.0,
                            constraint_name,
                        )


def create_shadow_price_constraints(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        for critical_branch_name in pricing.input_dataset.critical_branches:
            shadow_price = pricing.model.get_variable(constants.shadow_price_variable_name(critical_branch_name, time))
            saturated_critical_branch = pricing.saturated_critical_branch[critical_branch_name, time]
            if saturated_critical_branch > pricing.parameters.allowed_round_off_error:
                pricing.model.add_constraint(
                    saturated_critical_branch * shadow_price == 0.0,
                    constants.shadow_price_constraint_name(critical_branch_name, time),
                )


def create_adverse_flow_constraint(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        for border_name, border in pricing.input_dataset.market_borders.items():
            border_exchange = pricing.clearing_border_exchanges[border_name, time]
            if abs(border_exchange) < pricing.parameters.allowed_round_off_error:
                continue
            price_in, price_out = None, None
            for price_group in pricing.price_groups[time]:
                if border.uphill_market_area.name in price_group.market_area_names:
                    price_in = pricing.model.get_variable(constants.price_on_group_variable_name(price_group.id, time))
                if border.downhill_market_area.name in price_group.market_area_names:
                    price_out = pricing.model.get_variable(constants.price_on_group_variable_name(price_group.id, time))

            if price_in and not price_out:
                pricing.model.add_constraint(
                    -border_exchange * price_in >= 0.0,
                    constants.adverse_flow_constraint_name(border_name, time),
                )
            elif price_out and not price_in:
                pricing.model.add_constraint(
                    border_exchange * price_out >= 0.0,
                    constants.adverse_flow_constraint_name(border_name, time),
                )


def create_absolute_price_group_constraint(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        for price_group in pricing.price_groups[time]:
            positive_price = pricing.model.get_variable(
                constants.positive_price_on_group_variable_name(price_group.id, time)
            )
            negative_price = pricing.model.get_variable(
                constants.negative_price_on_group_variable_name(price_group.id, time)
            )
            price = pricing.model.get_variable(constants.price_on_group_variable_name(price_group.id, time))
            pricing.model.add_constraint(
                positive_price + negative_price - price == 0.0,
                constants.absolute_price_group_constraint_name(price_group.id, time),
            )


def create_branch_load_constraint(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        price_groups = pricing.price_groups[time]
        if count_saturated(pricing.saturated_critical_branch, time, pricing.parameters.allowed_round_off_error) != 0:
            continue
        for group_i, group_j in iter_group_pairs(price_groups):
            price = pricing.model.get_variable(constants.price_on_group_variable_name(group_i.id, time))
            other_price = pricing.model.get_variable(constants.price_on_group_variable_name(group_j.id, time))
            branch_load = price - other_price
            if pricing.parameters.fb_branch_load_slack_penalty:
                positive_slack = pricing.model.get_variable(
                    constants.positive_slack_branch_load_variable_name(group_i.id, group_j.id, time)
                )
                negative_slack = pricing.model.get_variable(
                    constants.negative_slack_branch_load_variable_name(group_i.id, group_j.id, time)
                )
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
                        shadow_prices_fb = pricing.model.get_variable(
                            constants.shadow_price_variable_name(critical_branch_name, time)
                        )
                        branch_load += coeff * mc_market_area_ptdf.day_ahead_ptdf.get_value(time) * shadow_prices_fb

            pricing.model.add_constraint(
                branch_load == 0.0,
                constants.price_ptdf_constraint_name(group_i.id, group_j.id, time),
            )


def create_add_price_difference_constraint(pricing: _PricingPhase) -> None:
    for time in pricing.input_dataset.times:
        price_groups = pricing.price_groups[time]
        for group_i, group_j in iter_group_pairs(price_groups):
            if not pricing.is_neighbour(group_i, group_j):
                continue
            price = pricing.model.get_variable(constants.price_on_group_variable_name(group_i.id, time))
            other_price = pricing.model.get_variable(constants.price_on_group_variable_name(group_j.id, time))
            positive_price_diff = pricing.model.get_variable(
                constants.positive_price_diff_on_group_variable_name(group_i.id, group_j.id, time)
            )
            negative_price_diff = pricing.model.get_variable(
                constants.negative_price_diff_on_group_variable_name(group_i.id, group_j.id, time)
            )

            pricing.model.add_constraint(
                positive_price_diff + negative_price_diff == price - other_price,
                constants.price_difference_constraint_name(group_i.id, group_j.id, time),
            )


def create_groups_prices_objective(pricing: _PricingPhase) -> None:
    objective = []
    for time in pricing.input_dataset.times:
        for price_group in pricing.price_groups[time]:
            price = pricing.model.get_variable(constants.price_on_group_variable_name(price_group.id, time))
            objective.append(pricing.parameters.market_price_penalty_alpha * price)
    pricing.model.add_objective(sum(objective))


def create_absolute_price_objective(pricing: _PricingPhase) -> None:
    objective = []
    for time in pricing.input_dataset.times:
        for price_group in pricing.price_groups[time]:
            positive_price = pricing.model.get_variable(
                constants.positive_price_on_group_variable_name(price_group.id, time)
            )
            negative_price = pricing.model.get_variable(
                constants.negative_price_on_group_variable_name(price_group.id, time)
            )
            objective.append(pricing.parameters.market_price_penalty_beta * (positive_price - negative_price))
    pricing.model.add_objective(sum(objective))


def create_branch_load_objective(pricing: _PricingPhase) -> None:
    objective = []
    for time in pricing.input_dataset.times:
        if count_saturated(pricing.saturated_critical_branch, time, pricing.parameters.allowed_round_off_error) != 0:
            continue
        price_groups = pricing.price_groups[time]
        for group_i, group_j in iter_group_pairs(price_groups):
            positive_load_slack = pricing.model.get_variable(
                constants.positive_slack_branch_load_variable_name(group_i.id, group_j.id, time)
            )
            negative_load_slack = pricing.model.get_variable(
                constants.negative_slack_branch_load_variable_name(group_i.id, group_j.id, time)
            )
            objective.append(
                pricing.parameters.fb_branch_load_slack_penalty * (positive_load_slack - negative_load_slack)
            )
    pricing.model.add_objective(sum(objective))


def create_groups_price_diff_objective(pricing: _PricingPhase) -> None:
    objective = []
    for time in pricing.input_dataset.times:
        price_groups = pricing.price_groups[time]
        for group_i, group_j in iter_group_pairs(price_groups):
            if not pricing.is_neighbour(group_i, group_j):
                continue
            positive_price_diff = pricing.model.get_variable(
                constants.positive_price_diff_on_group_variable_name(group_i.id, group_j.id, time)
            )
            negative_price_diff = pricing.model.get_variable(
                constants.negative_price_diff_on_group_variable_name(group_i.id, group_j.id, time)
            )
            objective.append(
                pricing.parameters.fb_branch_load_slack_penalty * (positive_price_diff - negative_price_diff)
            )
    pricing.model.add_objective(sum(objective))
