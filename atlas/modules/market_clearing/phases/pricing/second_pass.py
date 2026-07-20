"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Second pricing pass: run when the first pass is infeasible. Tightens each price group's bounds
to the accepted-orders-only range, then relaxes the marginal-order surplus constraint by
penalizing the worst rejected sale/buy instead of forcing it to zero.
"""

import atlas.modules.market_clearing.constants as constants
from atlas.config import logger
from atlas.modules.market_clearing.phases.pricing._types import _PricingPhase


def build_variables(pricing: _PricingPhase) -> None:
    """Create all variables for the second pricing phase model"""
    create_surplus_rejected_variables(pricing)


def build_constraints(pricing: _PricingPhase) -> None:
    """Create all constraints for the second pricing phase model"""
    deactivate_null_marginal_order_constraint(pricing)
    create_min_surplus_rejected_sale_constraints(pricing)
    create_max_surplus_rejected_buy_constraints(pricing)


def build_objective(pricing: _PricingPhase) -> None:
    """Create objective function for the second pricing phase model"""
    create_surplus_objective(pricing)


def update_price_bound(pricing: _PricingPhase) -> None:
    for price_group_list in pricing.price_groups.values():
        for price_group in price_group_list:
            price_group.max_price = float("inf")
            price_group.min_price = -float("inf")
            pricing.compute_price_bounds(price_group, 2)
            logger.debug(
                f"Updating price variables for group {(price_group.time_index, price_group.id)} with bounds "
                f"{price_group.min_price} and {price_group.max_price}"
            )
            price_group_variable = pricing.model.get_variable(
                constants.price_on_group_variable_name(price_group.id, price_group.time_index)
            )
            price_group_variable.SetLb(price_group.min_price)
            price_group_variable.SetUb(price_group.max_price)


def compute_min_max_rejected_sale_buy(pricing: _PricingPhase) -> None:
    for time_index, price_groups in pricing.price_groups.items():
        for price_group in price_groups:
            price_group.min_rejected_sale = float("inf")
            price_group.max_rejected_buy = -float("inf")
            for market_area_name in price_group.market_area_names:
                mc_market_area = pricing.input_dataset.mc_market_areas[market_area_name]

                for mc_order in mc_market_area.mc_orders.values():
                    # Keep only orders in correct time
                    if mc_order.time_index != time_index or mc_order.price is None:
                        continue
                    local_acc_power = pricing.clearing_accepted_powers[market_area_name, mc_order.name]
                    # Keep only rejected orders
                    if abs(mc_order.qmax - local_acc_power) > pricing.parameters.allowed_round_off_error:
                        if mc_order.is_sale:
                            price_group.min_rejected_sale = min(mc_order.price, price_group.min_rejected_sale)
                        else:
                            price_group.max_rejected_buy = max(mc_order.price, price_group.max_rejected_buy)
            logger.debug(f"Worst rejected : {price_group.min_rejected_sale}, {price_group.max_rejected_buy}")


def create_surplus_rejected_variables(pricing: _PricingPhase) -> None:
    for price_group_list in pricing.price_groups.values():
        for price_group in price_group_list:
            pricing.model.add_continuous_variable(
                constants.worst_rej_sale_group(price_group.id, price_group.time_index),
                0.0,
                float("inf"),
            )
            pricing.model.add_continuous_variable(
                constants.worst_rej_buy_group(price_group.id, price_group.time_index),
                0.0,
                float("inf"),
            )


def deactivate_null_marginal_order_constraint(pricing: _PricingPhase) -> None:
    for mc_order in pricing.input_dataset.mc_orders.values():
        if mc_order.name not in pricing._full_link_id_by_order and mc_order.parent_child_id is None:
            time_index = mc_order.time_index
            if time_index is None:
                continue

            local_cleared_power = pricing.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]

            if local_cleared_power > pricing.parameters.allowed_round_off_error:
                equipment_name = mc_order.equipment.name if mc_order.equipment else "NA"
                # MARGINAL SURPLUS: if the bid is not linked and marginally accepted, its surplus should be null
                if not mc_order.is_linked:
                    if (
                        abs(local_cleared_power - mc_order.qmin) >= pricing.parameters.allowed_round_off_error
                        and abs(local_cleared_power - mc_order.qmax) >= pricing.parameters.allowed_round_off_error
                    ):
                        constraint_name = constants.null_marginal_order_constraint_name(
                            mc_order.name, equipment_name, mc_order.market_area.name, time_index
                        )
                        pricing.model.deactivate_constraint(constraint_name)


def create_min_surplus_rejected_sale_constraints(pricing: _PricingPhase) -> None:
    for time_index, price_groups in pricing.price_groups.items():
        for price_group in price_groups:
            current_price = pricing.model.get_variable(
                constants.price_on_group_variable_name(price_group.id, time_index)
            )

            logger.debug(f"New bounds : {current_price.lb()}, {current_price.ub()}")
            min_rejected_sale = pricing.model.get_variable(constants.worst_rej_sale_group(price_group.id, time_index))
            pricing.model.add_constraint(
                min_rejected_sale - (current_price - price_group.min_rejected_sale) >= 0.0,
                constants.pos_min_rej_sale_group_constraint_name(price_group.id, time_index),
            )


def create_max_surplus_rejected_buy_constraints(pricing: _PricingPhase) -> None:
    for time_index, price_groups in pricing.price_groups.items():
        for price_group in price_groups:
            current_price = pricing.model.get_variable(
                constants.price_on_group_variable_name(price_group.id, time_index)
            )

            logger.debug(f"New bounds : {current_price.lb()}, {current_price.ub()}")
            max_rejected_buy = pricing.model.get_variable(constants.worst_rej_buy_group(price_group.id, time_index))
            pricing.model.add_constraint(
                max_rejected_buy - (price_group.max_rejected_buy - current_price) >= 0.0,
                constants.pos_max_rej_buy_group_constraint_name(price_group.id, time_index),
            )


def create_surplus_objective(pricing: _PricingPhase) -> None:
    objective = []
    for price_groups in pricing.price_groups.values():
        for price_group in price_groups:
            max_rejected_buy = pricing.model.get_variable(
                constants.worst_rej_buy_group(price_group.id, price_group.time_index)
            )
            min_rejected_sale = pricing.model.get_variable(
                constants.worst_rej_sale_group(price_group.id, price_group.time_index)
            )
            objective.append(pricing.parameters.paradoxically_rejected_penalty * (min_rejected_sale + max_rejected_buy))
    pricing.model.add_objective(sum(objective))
