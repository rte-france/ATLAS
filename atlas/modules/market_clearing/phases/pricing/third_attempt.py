"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Third pricing attempt: run when the second attempt is still infeasible. Deactivates the remaining
positive-surplus constraints and instead penalizes any paradoxically accepted/rejected order by
its opposite delta-P (the gap between its own price and the clearing price it actually got).
"""

import atlas.modules.market_clearing.constants as constants
from atlas.config import logger
from atlas.modules.market_clearing.phases.pricing._types import _PricingPhase


def build_variables(pricing: _PricingPhase, opposite_delta_p_dict: dict[int, float | None]) -> None:
    """Create all variables for the third pricing phase model"""
    create_delta_price_lo_variables(pricing)
    create_delta_price_pc_variables(pricing, opposite_delta_p_dict)
    create_delta_price_order_variables(pricing)


def build_constraints(pricing: _PricingPhase, opposite_delta_p_dict: dict[int, float | None]) -> None:
    """Create all constraints for the third pricing phase model"""
    deactivate_positive_surplus_lo_constraints(pricing)
    deactivate_negative_surplus_pc_constraints(pricing)
    deactivate_positive_surplus_pc_constraints(pricing)
    deactivate_positive_surplus_order_constraints(pricing)
    create_paradoxical_delta_price_lo_constraints(pricing)
    create_paradoxical_delta_price_pc_constraints(pricing, opposite_delta_p_dict)
    create_paradoxical_delta_price_order_constraints(pricing)


def build_objective(pricing: _PricingPhase, opposite_delta_p_dict: dict[int, float | None]) -> None:
    """Create objective function for the third pricing phase model"""
    create_paradoxical_lo_objective(pricing)
    create_paradoxical_pc_objective(pricing, opposite_delta_p_dict)
    create_paradoxical_order_objective(pricing)


def compute_opposite_delta_p(pricing: _PricingPhase) -> dict[int, float | None]:
    opposite_delta_p_dict: dict[int, float | None] = {}
    for index_pc, (parent_orders, children_orders) in pricing.dict_parent_child_orders.items():
        opposite_delta_p = None
        for order in parent_orders + children_orders:
            order = pricing.input_dataset.orders[order.name]
            time_index = order.time_index
            if time_index is None or order.group_index is None:
                continue
            local_cleared_power = pricing.clearing_accepted_powers[order.market_area.name, order.name]
            local_price = pricing.model.get_variable(
                constants.price_on_group_variable_name(order.group_index, time_index)
            )
            coeff_sale = order.production_sign

            # If order is accepted, add its delta P to the overall paradoxical delta P of this group of linked orders
            if local_cleared_power > pricing.parameters.allowed_round_off_error:
                delta = coeff_sale * (order.price - local_price)
                opposite_delta_p = delta if opposite_delta_p is None else opposite_delta_p + delta
        opposite_delta_p_dict[index_pc] = opposite_delta_p
    return opposite_delta_p_dict


def create_delta_price_lo_variables(pricing: _PricingPhase) -> None:
    for index_lo in pricing.dict_linked_orders:
        pricing.model.add_continuous_variable(constants.delta_p_lo(index_lo), 0, float("inf"))


def create_delta_price_pc_variables(pricing: _PricingPhase, opposite_delta_p_dict: dict[int, float | None]) -> None:
    for index_pc in pricing.dict_parent_child_orders:
        if opposite_delta_p_dict[index_pc] is not None:
            pricing.model.add_continuous_variable(constants.delta_p_pc(index_pc), 0, float("inf"))


def create_delta_price_order_variables(pricing: _PricingPhase) -> None:
    for order in pricing.input_dataset.orders.values():
        if order.name not in pricing._full_link_id_by_order and order.parent_child_id is None:
            if order.requires_status_variable is None or order.parent_child_id is not None:
                continue
            time_index = order.time_index
            if time_index is None:
                continue
            local_cleared_power = pricing.clearing_accepted_powers[order.market_area.name, order.name]

            if local_cleared_power > pricing.parameters.allowed_round_off_error:
                pricing.model.add_continuous_variable(
                    constants.delta_p_order(order.name, order.market_area.name, time_index), 0, float("inf")
                )


def deactivate_positive_surplus_lo_constraints(pricing: _PricingPhase) -> None:
    for index_lo in pricing.dict_linked_orders:
        constraint_name = constants.linked_bids_surplus_constraint_name(index_lo)
        if constraint_name:
            pricing.model.deactivate_constraint(constraint_name)


def deactivate_negative_surplus_pc_constraints(pricing: _PricingPhase) -> None:
    for index_pc in pricing.dict_parent_child_orders:
        constraint_name = constants.negative_parent_child_surplus_constraint_name(index_pc)
        if constraint_name:
            # If there is surplus
            if constraint_name in pricing.model.constraints:
                pricing.model.deactivate_constraint(constraint_name)
            else:
                logger.debug(f"No surplus for {index_pc}")


def deactivate_positive_surplus_pc_constraints(pricing: _PricingPhase) -> None:
    for index_pc, (_, children_orders) in pricing.dict_parent_child_orders.items():
        index_child = 0
        for order in children_orders:
            order = pricing.input_dataset.orders[order.name]
            time_index = order.time_index
            if time_index is None:
                continue
            local_cleared_power = pricing.clearing_accepted_powers[order.market_area.name, order.name]
            if local_cleared_power > pricing.parameters.allowed_round_off_error:
                constraint_name = constants.positive_parent_child_surplus_constraint_name(
                    index_child, index_pc, time_index
                )
                pricing.model.deactivate_constraint(constraint_name)
                index_child += 1


def deactivate_positive_surplus_order_constraints(pricing: _PricingPhase) -> None:
    for order in pricing.input_dataset.orders.values():
        if order.name not in pricing._full_link_id_by_order and order.parent_child_id is None:
            if order.requires_status_variable is not None and order.parent_child_id is None:
                time_index = order.time_index
                if time_index is None:
                    continue
                local_cleared_power = pricing.clearing_accepted_powers[order.market_area.name, order.name]

                if local_cleared_power > pricing.parameters.allowed_round_off_error:
                    equipment_name = order.equipment.name if order.equipment else "NA"
                    constraint_name = constants.pos_surplus_order_constraint_name(
                        order.name, equipment_name, order.market_area.name, time_index
                    )
                    if constraint_name:
                        pricing.model.deactivate_constraint(constraint_name)


def create_paradoxical_delta_price_order_constraints(pricing: _PricingPhase) -> None:
    for order in pricing.input_dataset.orders.values():
        if order.name not in pricing._full_link_id_by_order and order.parent_child_id is None:
            if order.requires_status_variable is not None and order.parent_child_id is None:
                local_cleared_power = pricing.clearing_accepted_powers[order.market_area.name, order.name]
                if local_cleared_power > pricing.parameters.allowed_round_off_error:
                    time_index = order.time_index
                    if time_index is None or order.group_index is None:
                        continue
                    local_price = pricing.model.get_variable(
                        constants.price_on_group_variable_name(order.group_index, time_index)
                    )
                    coeff_sale = order.production_sign
                    opposite_delta_p = coeff_sale * (order.price - local_price)
                    paradoxical_delta_p = pricing.model.get_variable(
                        constants.delta_p_order(order.name, order.market_area.name, time_index)
                    )
                    pricing.model.add_constraint(
                        paradoxical_delta_p >= opposite_delta_p,
                        constants.paradoxical_delta_p_order_constraint_name(
                            order.name, order.market_area.name, time_index
                        ),
                    )


def create_paradoxical_lo_objective(pricing: _PricingPhase) -> None:
    objective = []
    for index_lo in pricing.dict_linked_orders:
        delta_p = pricing.model.get_variable(constants.delta_p_lo(index_lo))
        objective.append(pricing.parameters.paradoxically_accepted_penalty * delta_p)
    pricing.model.add_objective(sum(objective))


def create_paradoxical_pc_objective(pricing: _PricingPhase, opposite_delta_p_dict: dict[int, float | None]) -> None:
    objective = []
    for index_pc in pricing.dict_parent_child_orders:
        if opposite_delta_p_dict[index_pc] is not None:
            delta_p = pricing.model.get_variable(constants.delta_p_pc(index_pc))
            objective.append(pricing.parameters.paradoxically_accepted_penalty * delta_p)
    pricing.model.add_objective(sum(objective))


def create_paradoxical_order_objective(pricing: _PricingPhase) -> None:
    objective = []
    for order in pricing.input_dataset.orders.values():
        if order.name not in pricing._full_link_id_by_order and order.parent_child_id is None:
            if order.requires_status_variable is None or order.parent_child_id is not None:
                continue
            time_index = order.time_index
            if time_index is None:
                continue
            local_cleared_power = pricing.clearing_accepted_powers[order.market_area.name, order.name]

            if local_cleared_power > pricing.parameters.allowed_round_off_error:
                delta_p = pricing.model.get_variable(
                    constants.delta_p_order(order.name, order.market_area.name, time_index)
                )
                objective.append(pricing.parameters.paradoxically_accepted_penalty * delta_p)
    pricing.model.add_objective(sum(objective))


def create_paradoxical_delta_price_pc_constraints(
    pricing: _PricingPhase, opposite_delta_p_dict: dict[int, float | None]
) -> None:
    for index_pc in pricing.dict_parent_child_orders:
        if opposite_delta_p_dict[index_pc] is not None:
            paradoxical_delta_p = pricing.model.get_variable(constants.delta_p_pc(index_pc))
            pricing.model.add_constraint(
                paradoxical_delta_p >= opposite_delta_p_dict[index_pc],
                constants.paradoxical_delta_p_pc_constraint_name(index_pc),
            )


def create_paradoxical_delta_price_lo_constraints(pricing: _PricingPhase) -> None:
    for index_lo, orders in pricing.dict_linked_orders.items():
        paradoxical_delta_p = pricing.model.get_variable(constants.delta_p_lo(index_lo))
        opposite_delta_p = 0
        for order in orders:
            order = pricing.input_dataset.orders[order.name]
            time_index = order.time_index
            if time_index is None or order.group_index is None:
                continue
            local_cleared_power = pricing.clearing_accepted_powers[order.market_area.name, order.name]
            local_price = pricing.model.get_variable(
                constants.price_on_group_variable_name(order.group_index, time_index)
            )
            coeff_sale = order.production_sign

            # If order is accepted, add its delta P to the overall paradoxical delta P of this group of linked orders
            if local_cleared_power > pricing.parameters.allowed_round_off_error:
                opposite_delta_p += coeff_sale * (order.price - local_price)

        pricing.model.add_constraint(
            paradoxical_delta_p >= opposite_delta_p, constants.paradoxical_delta_p_lo_constraint_name(index_lo)
        )
