"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import json

import atlas.modules.market_clearing.constants as constants
from atlas.config import logger
from atlas.enums import SolverStatus
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_area import MarketAreaMC
from atlas.modules.market_clearing.input_objects.market_border import MarketBorderMC
from atlas.modules.market_clearing.order_links import OrderLinkResolver
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases._helpers import count_saturated, iter_group_pairs
from atlas.modules.market_clearing.price_group import PriceGroup
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel


class Pricing:
    def __init__(
        self,
        input_dataset: MarketClearingInputDataset,
        parameters: MarketClearingParameters,
        saturated_critical_branch: dict[tuple[str, int], float],
        exchange_fixing_border_exchanges: dict[tuple[str, int], float],
        clearing_local_balances: dict[tuple[str, int], float],
        clearing_accepted_powers: dict[tuple[str, str], float],
    ):
        solver_options = SolverOptions(presolve=parameters.solver.use_presolve)

        self.model = OptimisationModel(parameters.solver.solver_name, options=solver_options, name="Pricing")
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.saturated_critical_branch = saturated_critical_branch
        self.clearing_border_exchanges = exchange_fixing_border_exchanges
        self.clearing_local_balances = clearing_local_balances
        self.clearing_accepted_powers = clearing_accepted_powers
        self.price_groups = self.create_price_groups()
        order_links = OrderLinkResolver(self.input_dataset.mc_orders, self.input_dataset.mc_order_couplings).resolve()
        self.dict_linked_orders = order_links.linked_orders
        self.dict_parent_child_orders = order_links.parent_child_orders
        self._full_link_id_by_order = order_links.full_link_id_by_order

    def compute(self):
        self.build_first()
        solver_info = self.model.solve()
        output_path = self.parameters.get_lp_dir()
        if self.parameters.solver.export_lp:
            output_path.mkdir(parents=True, exist_ok=True)
            self.model.export_model(str(output_path / "pricing_1_model.lp"))
        if solver_info.status not in [SolverStatus.OPTIMAL, SolverStatus.FEASIBLE]:
            self.build_second()
            solver_info = self.model.solve()
            if self.parameters.solver.export_lp:
                self.model.export_model(str(output_path / "pricing_2_model.lp"))

        if solver_info.status not in [SolverStatus.OPTIMAL, SolverStatus.FEASIBLE]:
            self.build_third()
            _ = self.model.solve()
            if self.parameters.solver.export_lp:
                self.model.export_model(str(output_path / "pricing_3_model.lp"))
        if self.parameters.solver.export_lp:
            with open(output_path / "pricing_market_prices.json", "w") as f:
                json.dump(
                    [
                        [market_area_name, time_index, val]
                        for (market_area_name, time_index), val in self.get_market_prices().items()
                    ],
                    f,
                )

    def build_first(self):
        self.instantiate_order_group_index()
        self.build_first_variables()
        self.build_first_constraints()
        self.build_first_objective()

    def build_first_variables(self):
        """Create all variables for the first pricing phase model"""
        # Define surplus on the corresponding sets
        self.create_price_variables()
        self.create_positive_price_variables()
        self.create_negative_price_variables()
        self.create_positive_diff_price_variables()
        self.create_negative_diff_price_variables()
        if self.parameters.fb_branch_load_slack_penalty:
            self.create_positive_slack_branch_load_variables()
            self.create_negative_slack_branch_load_variables()
        self.create_shadow_price_variables()
        self.create_link_child_to_pc_variables()

    def build_first_constraints(self):
        """Create all constraints for the first pricing phase model"""
        if self.parameters.prevent_adverse_flows:
            self.create_adverse_flow_constraint()
        if self.parameters.market_price_penalty_beta:
            self.create_absolute_price_group_constraint()
        if not self.input_dataset.is_atc:
            self.create_branch_load_constraint()
        self.create_add_price_difference_constraint()
        self.create_shadow_price_constraints()
        self.create_linked_bid_surplus_constraints()
        self.create_parent_child_surplus_constraints()
        self.create_pos_surplus_order_constraints()
        self.create_null_marginal_order_constraints()

    def build_first_objective(self):
        """Create objective function for the first pricing phase model"""
        self.model.set_direction("minimize")
        if self.parameters.market_price_penalty_alpha:
            self.create_groups_prices_objective()
        if self.parameters.market_price_penalty_beta:
            self.create_absolute_price_objective()
        if not self.input_dataset.is_atc and self.parameters.fb_branch_load_slack_penalty:
            self.create_branch_load_objective()
        self.create_groups_price_diff_objective()

    def build_second(self):
        # Update PriceGroup
        self.update_price_bound()
        self.compute_min_max_rejected_sale_buy()
        self.build_second_variables()
        # If the order is accepted, check if it is partially accepted. If so, delete the marginal surplus constraint.
        self.build_second_constraints()
        self.build_second_objective()

    def build_second_variables(self):
        """Create all variables for the second pricing phase model"""
        self.create_surplus_rejected_variables()

    def build_second_constraints(self):
        """Create all constraints for the second pricing phase model"""
        self.deactivate_null_marginal_order_constraint()
        self.create_min_surplus_rejected_sale_constraints()
        self.create_max_surplus_rejected_buy_constraints()

    def build_second_objective(self):
        """Create objective function for the second pricing phase model"""
        self.create_surplus_objective()

    def build_third(self):
        opposite_delta_p_dict = self.compute_opposite_delta_p()
        self.build_third_variables(opposite_delta_p_dict)
        self.build_third_constraints(opposite_delta_p_dict)
        self.build_third_objective(opposite_delta_p_dict)

    def build_third_variables(self, opposite_delta_p_dict: dict[int, float | None]):
        """Create all variables for the third pricing phase model"""
        self.create_delta_price_lo_variables()
        self.create_delta_price_pc_variables(opposite_delta_p_dict)
        self.create_delta_price_order_variables()

    def build_third_constraints(self, opposite_delta_p_dict: dict[int, float | None]):
        """Create all constraints for the third pricing phase model"""
        self.deactivate_positive_surplus_lo_constraints()
        self.deactivate_negative_surplus_pc_constraints()
        self.deactivate_positive_surplus_pc_constraints()
        self.deactivate_positive_surplus_order_constraints()
        self.create_paradoxical_delta_price_lo_constraints()
        self.create_paradoxical_delta_price_pc_constraints(opposite_delta_p_dict)
        self.create_paradoxical_delta_price_order_constraints()

    def build_third_objective(self, opposite_delta_p_dict: dict[int, float | None]):
        """Create objective function for the third pricing phase model"""
        self.create_paradoxical_lo_objective()
        self.create_paradoxical_pc_objective(opposite_delta_p_dict)
        self.create_paradoxical_order_objective()

    ##################################
    # Variables
    ##################################
    def create_link_child_to_pc_variables(self):
        for index_pc, (_, child_orders) in self.dict_parent_child_orders.items():
            index_child = 0
            for child_order in child_orders:
                child_mc_order = self.input_dataset.mc_orders[child_order.name]
                local_cleared_power = self.clearing_accepted_powers[
                    child_mc_order.market_area.name, child_mc_order.name
                ]
                if local_cleared_power > self.parameters.allowed_round_off_error:
                    self.model.add_continuous_variable(
                        constants.link_child_to_pc(index_child, index_pc), 0, float("inf")
                    )
                    index_child += 1

    def create_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                self.model.add_continuous_variable(
                    constants.price_on_group_variable_name(price_group.id, time_index),
                    -float("inf"),
                    float("inf"),
                )

    def create_positive_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                self.model.add_continuous_variable(
                    constants.positive_price_on_group_variable_name(price_group.id, time_index),
                    0.0,
                    float("inf"),
                )

    def create_negative_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                self.model.add_continuous_variable(
                    constants.negative_price_on_group_variable_name(price_group.id, time_index),
                    -float("inf"),
                    0.0,
                )

    def create_positive_diff_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            for group_i, group_j in iter_group_pairs(price_groups):
                self.model.add_continuous_variable(
                    constants.positive_price_diff_on_group_variable_name(group_i.id, group_j.id, time_index),
                    0.0,
                    float("inf"),
                )

    def create_negative_diff_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            for group_i, group_j in iter_group_pairs(price_groups):
                self.model.add_continuous_variable(
                    constants.negative_price_diff_on_group_variable_name(group_i.id, group_j.id, time_index),
                    -float("inf"),
                    0.0,
                )

    def create_shadow_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for critical_branch_name in self.input_dataset.mc_critical_branches:
                self.model.add_continuous_variable(
                    constants.shadow_price_variable_name(critical_branch_name, time_index),
                    -float("inf"),
                    0.0,
                )

    def create_positive_slack_branch_load_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            if (
                count_saturated(self.saturated_critical_branch, time_index, self.parameters.allowed_round_off_error)
                != 0
            ):
                continue
            for group_i, group_j in iter_group_pairs(price_groups):
                self.model.add_continuous_variable(
                    constants.positive_slack_branch_load_variable_name(group_i.id, group_j.id, time_index),
                    0.0,
                    float("inf"),
                )

    def create_negative_slack_branch_load_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            if (
                count_saturated(self.saturated_critical_branch, time_index, self.parameters.allowed_round_off_error)
                != 0
            ):
                continue
            for group_i, group_j in iter_group_pairs(price_groups):
                self.model.add_continuous_variable(
                    constants.negative_slack_branch_load_variable_name(group_i.id, group_j.id, time_index),
                    -float("inf"),
                    0.0,
                )

    ##################################
    # Constraints
    ##################################
    def create_linked_bid_surplus_constraints(self):
        for index_lo, orders in self.dict_linked_orders.items():
            logger.debug(f"Surplus for : {index_lo}")
            surplus = 0
            for order in orders:
                mc_order = self.input_dataset.mc_orders[order.name]
                time_index = mc_order.time_index
                local_price = self.model.get_variable(
                    constants.price_on_group_variable_name(mc_order.group_index, time_index)
                )
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]
                coeff_sale = mc_order.production_sign

                # If order is accepted, add its surplus to the overall surplus of this group of linked orders
                if local_cleared_power > self.parameters.allowed_round_off_error:
                    surplus += coeff_sale * local_cleared_power * (local_price - mc_order.price)

            self.model.add_constraint(
                surplus >= 0.0,
                constants.linked_bids_surplus_constraint_name(index_lo),
            )

    # Global parent_child bids' surplus
    def create_parent_child_surplus_constraints(self):
        for index_pc, (parent_orders, child_orders) in self.dict_parent_child_orders.items():
            index_child = 0
            logger.debug(f"Surplus for PC {index_pc}")

            sum_children_link_surplus = 0

            # Setting constraints individually for child orders
            for child_order in child_orders:
                child_mc_order = self.input_dataset.mc_orders[child_order.name]
                time_index = child_mc_order.time_index

                local_price = self.model.get_variable(
                    constants.price_on_group_variable_name(child_mc_order.group_index, time_index)
                )
                local_cleared_power = self.clearing_accepted_powers[
                    child_mc_order.market_area.name, child_mc_order.name
                ]
                coeff_sale = child_mc_order.production_sign

                if local_cleared_power > self.parameters.allowed_round_off_error:
                    link_surplus = self.model.get_variable(constants.link_child_to_pc(index_child, index_pc))
                    sum_children_link_surplus += link_surplus
                    logger.debug(f"surplus child {index_child} PC {index_pc}")
                    self.model.add_constraint(
                        (coeff_sale * local_cleared_power * (local_price - child_mc_order.price) - link_surplus) >= 0.0,
                        constants.positive_parent_child_surplus_constraint_name(index_child, index_pc, time_index),
                    )
                    index_child += 1

            # Then set global constraint on parents
            surplus = 0
            for parent_order in parent_orders:
                parent_mc_order = self.input_dataset.mc_orders[parent_order.name]
                time_index = parent_mc_order.time_index

                local_price = self.model.get_variable(
                    constants.price_on_group_variable_name(parent_mc_order.group_index, time_index)
                )
                local_cleared_power = self.clearing_accepted_powers[
                    parent_mc_order.market_area.name, parent_mc_order.name
                ]
                coeff_sale = parent_mc_order.production_sign

                # If order is accepted, add its surplus to the overall surplus of this group of linked orders
                if local_cleared_power > self.parameters.allowed_round_off_error:
                    surplus += coeff_sale * local_cleared_power * (local_price - parent_order.price)
            logger.debug(f"Surplus parent PC {index_pc}")
            if surplus:
                self.model.add_constraint(
                    surplus + sum_children_link_surplus >= 0.0,
                    constants.negative_parent_child_surplus_constraint_name(index_pc),
                )

    def create_pos_surplus_order_constraints(self):
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.name not in self._full_link_id_by_order and mc_order.parent_child_id is None:
                time_index = mc_order.time_index

                local_price = self.model.get_variable(
                    constants.price_on_group_variable_name(mc_order.group_index, time_index)
                )
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]

                if local_cleared_power > self.parameters.allowed_round_off_error:
                    coeff_sale = mc_order.production_sign
                    equipment_name = mc_order.equipment.name if mc_order.equipment else "NA"
                    self.model.add_constraint(
                        coeff_sale * local_cleared_power * (local_price - mc_order.price) >= 0.0,
                        constants.pos_surplus_order_constraint_name(
                            mc_order.name, equipment_name, mc_order.market_area.name, time_index
                        ),
                    )

    def create_null_marginal_order_constraints(self):
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.name not in self._full_link_id_by_order and mc_order.parent_child_id is None:
                time_index = mc_order.time_index

                local_price = self.model.get_variable(
                    constants.price_on_group_variable_name(mc_order.group_index, time_index)
                )
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]

                if local_cleared_power > self.parameters.allowed_round_off_error:
                    coeff_sale = mc_order.production_sign
                    equipment_name = mc_order.equipment.name if mc_order.equipment else "NA"
                    # MARGINAL SURPLUS: if the bid is not linked and marginally accepted, its surplus should be null
                    if not mc_order.is_linked:
                        if (
                            abs(local_cleared_power - mc_order.qmin) >= self.parameters.allowed_round_off_error
                            and abs(local_cleared_power - mc_order.qmax) >= self.parameters.allowed_round_off_error
                        ):
                            constraint_name = constants.null_marginal_order_constraint_name(
                                mc_order.name, equipment_name, mc_order.market_area.name, time_index
                            )
                            self.model.add_constraint(
                                coeff_sale * local_cleared_power * (local_price - mc_order.price) == 0.0,
                                constraint_name,
                            )

    def create_shadow_price_constraints(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for critical_branch_name in self.input_dataset.mc_critical_branches:
                shadow_price = self.model.get_variable(
                    constants.shadow_price_variable_name(critical_branch_name, time_index)
                )
                saturated_critical_branch = self.saturated_critical_branch[critical_branch_name, time_index]
                if saturated_critical_branch > self.parameters.allowed_round_off_error:
                    self.model.add_constraint(
                        saturated_critical_branch * shadow_price == 0.0,
                        constants.shadow_price_constraint_name(critical_branch_name, time_index),
                    )

    def create_adverse_flow_constraint(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for border_name, mc_border in self.input_dataset.mc_market_borders.items():
                border_exchange = self.clearing_border_exchanges[border_name, time_index]
                if abs(border_exchange) < self.parameters.allowed_round_off_error:
                    continue
                price_in, price_out = None, None
                for price_group in self.price_groups[time_index]:
                    if mc_border.uphill_market_area.name in price_group.market_area_names:
                        price_in = self.model.get_variable(
                            constants.price_on_group_variable_name(price_group.id, time_index)
                        )
                    if mc_border.downhill_market_area.name in price_group.market_area_names:
                        price_out = self.model.get_variable(
                            constants.price_on_group_variable_name(price_group.id, time_index)
                        )

                if price_in and not price_out:
                    self.model.add_constraint(
                        -border_exchange * price_in >= 0.0,
                        constants.adverse_flow_constraint_name(border_name, time_index),
                    )
                elif price_out and not price_in:
                    self.model.add_constraint(
                        border_exchange * price_out >= 0.0,
                        constants.adverse_flow_constraint_name(border_name, time_index),
                    )

    def create_absolute_price_group_constraint(self):
        for time_index, time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                positive_price = self.model.get_variable(
                    constants.positive_price_on_group_variable_name(price_group.id, time_index)
                )
                negative_price = self.model.get_variable(
                    constants.negative_price_on_group_variable_name(price_group.id, time_index)
                )
                price = self.model.get_variable(constants.price_on_group_variable_name(price_group.id, time_index))
                self.model.add_constraint(
                    positive_price + negative_price - price == 0.0,
                    constants.absolute_price_group_constraint_name(price_group.id, time),
                )
        return

    def create_branch_load_constraint(self):
        for time_index, time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            if (
                count_saturated(self.saturated_critical_branch, time_index, self.parameters.allowed_round_off_error)
                != 0
            ):
                continue
            for group_i, group_j in iter_group_pairs(price_groups):
                price = self.model.get_variable(constants.price_on_group_variable_name(group_i.id, time_index))
                other_price = self.model.get_variable(constants.price_on_group_variable_name(group_j.id, time_index))
                branch_load = price - other_price
                if self.parameters.fb_branch_load_slack_penalty:
                    positive_slack = self.model.get_variable(
                        constants.positive_slack_branch_load_variable_name(group_i.id, group_j.id, time_index)
                    )
                    negative_slack = self.model.get_variable(
                        constants.negative_slack_branch_load_variable_name(group_i.id, group_j.id, time_index)
                    )
                    branch_load += positive_slack + negative_slack
                for critical_branch_name, mc_critical_branch in self.input_dataset.mc_critical_branches.items():
                    for market_area_name in self.input_dataset.mc_market_areas:
                        if market_area_name in group_i.market_area_names:
                            coeff = 1.0
                        elif market_area_name in group_j.market_area_names:
                            coeff = -1.0
                        else:
                            continue

                        if market_area_name in mc_critical_branch.ptdf:
                            branch_ptdf = mc_critical_branch.ptdf[market_area_name]
                            shadow_prices_fb = self.model.get_variable(
                                constants.shadow_price_variable_name(critical_branch_name, time_index)
                            )
                            branch_load += coeff * branch_ptdf.get_value(time) * shadow_prices_fb

                self.model.add_constraint(
                    branch_load == 0.0,
                    constants.price_ptdf_constraint_name(group_i.id, group_j.id, time_index),
                )

    def create_add_price_difference_constraint(self):
        for time_index, time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            for group_i, group_j in iter_group_pairs(price_groups):
                if not self.is_neighbour(group_i, group_j):
                    continue
                price = self.model.get_variable(constants.price_on_group_variable_name(group_i.id, time_index))
                other_price = self.model.get_variable(constants.price_on_group_variable_name(group_j.id, time_index))
                positive_price_diff = self.model.get_variable(
                    constants.positive_price_diff_on_group_variable_name(group_i.id, group_j.id, time_index)
                )
                negative_price_diff = self.model.get_variable(
                    constants.negative_price_diff_on_group_variable_name(group_i.id, group_j.id, time_index)
                )

                self.model.add_constraint(
                    positive_price_diff + negative_price_diff == price - other_price,
                    constants.price_difference_constraint_name(group_i.id, group_j.id, time),
                )

    def create_groups_prices_objective(self):
        objective = []
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                price = self.model.get_variable(constants.price_on_group_variable_name(price_group.id, time_index))
                objective.append(self.parameters.market_price_penalty_alpha * price)
        return self.model.add_objective(sum(objective))

    def create_absolute_price_objective(self):
        objective = []
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                positive_price = self.model.get_variable(
                    constants.positive_price_on_group_variable_name(price_group.id, time_index)
                )
                negative_price = self.model.get_variable(
                    constants.negative_price_on_group_variable_name(price_group.id, time_index)
                )
                objective.append(self.parameters.market_price_penalty_beta * (positive_price - negative_price))
        return self.model.add_objective(sum(objective))

    def create_branch_load_objective(self):
        objective = []
        for time_index, _time in enumerate(self.input_dataset.times):
            if (
                count_saturated(self.saturated_critical_branch, time_index, self.parameters.allowed_round_off_error)
                != 0
            ):
                continue
            price_groups = self.price_groups[time_index]
            for group_i, group_j in iter_group_pairs(price_groups):
                positive_load_slack = self.model.get_variable(
                    constants.positive_slack_branch_load_variable_name(group_i.id, group_j.id, time_index)
                )
                negative_load_slack = self.model.get_variable(
                    constants.negative_slack_branch_load_variable_name(group_i.id, group_j.id, time_index)
                )
                objective.append(
                    self.parameters.fb_branch_load_slack_penalty * (positive_load_slack - negative_load_slack)
                )
        return self.model.add_objective(sum(objective))

    def create_groups_price_diff_objective(self):
        objective = []
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            for group_i, group_j in iter_group_pairs(price_groups):
                if not self.is_neighbour(group_i, group_j):
                    continue
                positive_price_diff = self.model.get_variable(
                    constants.positive_price_diff_on_group_variable_name(group_i.id, group_j.id, time_index)
                )
                negative_price_diff = self.model.get_variable(
                    constants.negative_price_diff_on_group_variable_name(group_i.id, group_j.id, time_index)
                )
                objective.append(
                    self.parameters.fb_branch_load_slack_penalty * (positive_price_diff - negative_price_diff)
                )
        return self.model.add_objective(sum(objective))

    # Second Pricing variables
    def create_surplus_rejected_variables(self):
        for price_group_list in self.price_groups.values():
            for price_group in price_group_list:
                self.model.add_continuous_variable(
                    constants.worst_rej_sale_group(price_group.id, price_group.time_index),
                    0.0,
                    float("inf"),
                )
                self.model.add_continuous_variable(
                    constants.worst_rej_buy_group(price_group.id, price_group.time_index),
                    0.0,
                    float("inf"),
                )

    def deactivate_null_marginal_order_constraint(self):
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.name not in self._full_link_id_by_order and mc_order.parent_child_id is None:
                time_index = mc_order.time_index

                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]

                if local_cleared_power > self.parameters.allowed_round_off_error:
                    equipment_name = mc_order.equipment.name if mc_order.equipment else "NA"
                    # MARGINAL SURPLUS: if the bid is not linked and marginally accepted, its surplus should be null
                    if not mc_order.is_linked:
                        if (
                            abs(local_cleared_power - mc_order.qmin) >= self.parameters.allowed_round_off_error
                            and abs(local_cleared_power - mc_order.qmax) >= self.parameters.allowed_round_off_error
                        ):
                            constraint_name = constants.null_marginal_order_constraint_name(
                                mc_order.name, equipment_name, mc_order.market_area.name, time_index
                            )
                            self.model.deactivate_constraint(constraint_name)

    def create_min_surplus_rejected_sale_constraints(self):
        for time_index, price_groups in self.price_groups.items():
            for price_group in price_groups:
                current_price = self.model.get_variable(
                    constants.price_on_group_variable_name(price_group.id, time_index)
                )

                logger.debug(f"New bounds : {current_price.lb()}, {current_price.ub()}")
                min_rejected_sale = self.model.get_variable(constants.worst_rej_sale_group(price_group.id, time_index))
                self.model.add_constraint(
                    min_rejected_sale - (current_price - price_group.min_rejected_sale) >= 0.0,
                    constants.pos_min_rej_sale_group_constraint_name(price_group.id, time_index),
                )

    def create_max_surplus_rejected_buy_constraints(self):
        for time_index, price_groups in self.price_groups.items():
            for price_group in price_groups:
                current_price = self.model.get_variable(
                    constants.price_on_group_variable_name(price_group.id, time_index)
                )

                logger.debug(f"New bounds : {current_price.lb()}, {current_price.ub()}")
                max_rejected_buy = self.model.get_variable(constants.worst_rej_buy_group(price_group.id, time_index))
                self.model.add_constraint(
                    max_rejected_buy - (price_group.max_rejected_buy - current_price) >= 0.0,
                    constants.pos_max_rej_buy_group_constraint_name(price_group.id, time_index),
                )

    def create_surplus_objective(self):
        objective = []
        for price_groups in self.price_groups.values():
            for price_group in price_groups:
                max_rejected_buy = self.model.get_variable(
                    constants.worst_rej_buy_group(price_group.id, price_group.time_index)
                )
                min_rejected_sale = self.model.get_variable(
                    constants.worst_rej_sale_group(price_group.id, price_group.time_index)
                )
                objective.append(
                    self.parameters.paradoxically_rejected_penalty * (min_rejected_sale + max_rejected_buy)
                )
        return self.model.add_objective(sum(objective))

    # Pricing 3
    def compute_opposite_delta_p(self) -> dict[int, float | None]:
        opposite_delta_p_dict: dict[int, float | None] = {}
        for index_pc, (parent_orders, children_orders) in self.dict_parent_child_orders.items():
            opposite_delta_p = None
            for order in parent_orders + children_orders:
                mc_order = self.input_dataset.mc_orders[order.name]
                time_index = mc_order.time_index
                if time_index is None or mc_order.group_index is None:
                    continue
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]
                local_price = self.model.get_variable(
                    constants.price_on_group_variable_name(mc_order.group_index, time_index)
                )
                coeff_sale = mc_order.production_sign

                # If order is accepted, add its delta P to the overall paradoxical delta P of this group of linked orders
                if local_cleared_power > self.parameters.allowed_round_off_error:
                    delta = coeff_sale * (mc_order.price - local_price)
                    opposite_delta_p = delta if opposite_delta_p is None else opposite_delta_p + delta
            opposite_delta_p_dict[index_pc] = opposite_delta_p
        return opposite_delta_p_dict

    def create_delta_price_lo_variables(self):
        for index_lo in self.dict_linked_orders:
            self.model.add_continuous_variable(constants.delta_p_lo(index_lo), 0, float("inf"))

    def create_delta_price_pc_variables(self, opposite_delta_p_dict: dict[int, float | None]):
        for index_pc in self.dict_parent_child_orders:
            if opposite_delta_p_dict[index_pc] is not None:
                self.model.add_continuous_variable(constants.delta_p_pc(index_pc), 0, float("inf"))

    def create_delta_price_order_variables(self):
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.name not in self._full_link_id_by_order and mc_order.parent_child_id is None:
                if mc_order.requires_status_variable is None or mc_order.parent_child_id is not None:
                    continue
                time_index = mc_order.time_index
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]

                if local_cleared_power > self.parameters.allowed_round_off_error:
                    self.model.add_continuous_variable(
                        constants.delta_p_order(mc_order.name, mc_order.market_area.name, time_index), 0, float("inf")
                    )

    def deactivate_positive_surplus_lo_constraints(self):
        for index_lo in self.dict_linked_orders:
            constraint_name = constants.linked_bids_surplus_constraint_name(index_lo)
            if constraint_name:
                self.model.deactivate_constraint(constraint_name)

    def deactivate_negative_surplus_pc_constraints(self):
        for index_pc in self.dict_parent_child_orders:
            constraint_name = constants.negative_parent_child_surplus_constraint_name(index_pc)
            if constraint_name:
                # If there is surplus
                if constraint_name in self.model.constraints:
                    self.model.deactivate_constraint(constraint_name)
                else:
                    logger.debug(f"No surplus for {index_pc}")

    def deactivate_positive_surplus_pc_constraints(self):
        for index_pc, (_, children_orders) in self.dict_parent_child_orders.items():
            index_child = 0
            for order in children_orders:
                mc_order = self.input_dataset.mc_orders[order.name]
                time_index = mc_order.time_index
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]
                if local_cleared_power > self.parameters.allowed_round_off_error:
                    constraint_name = constants.positive_parent_child_surplus_constraint_name(
                        index_child, index_pc, time_index
                    )
                    self.model.deactivate_constraint(constraint_name)
                    index_child += 1

    def deactivate_positive_surplus_order_constraints(self):
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.name not in self._full_link_id_by_order and mc_order.parent_child_id is None:
                if mc_order.requires_status_variable is not None and mc_order.parent_child_id is None:
                    local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]

                    if local_cleared_power > self.parameters.allowed_round_off_error:
                        equipment_name = mc_order.equipment.name if mc_order.equipment else "NA"
                        constraint_name = constants.pos_surplus_order_constraint_name(
                            mc_order.name, equipment_name, mc_order.market_area.name, mc_order.time_index
                        )
                        if constraint_name:
                            self.model.deactivate_constraint(constraint_name)

    def create_paradoxical_delta_price_order_constraints(self):
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.name not in self._full_link_id_by_order and mc_order.parent_child_id is None:
                if mc_order.requires_status_variable is not None and mc_order.parent_child_id is None:
                    local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]
                    if local_cleared_power > self.parameters.allowed_round_off_error:
                        time_index = mc_order.time_index
                        local_price = self.model.get_variable(
                            constants.price_on_group_variable_name(mc_order.group_index, time_index)
                        )
                        coeff_sale = mc_order.production_sign
                        opposite_delta_p = coeff_sale * (mc_order.price - local_price)
                        paradoxical_delta_p = self.model.get_variable(
                            constants.delta_p_order(mc_order.name, mc_order.market_area.name, time_index)
                        )
                        self.model.add_constraint(
                            paradoxical_delta_p >= opposite_delta_p,
                            constants.paradoxical_delta_p_order_constraint_name(
                                mc_order.name, mc_order.market_area.name, time_index
                            ),
                        )

    def create_paradoxical_lo_objective(self):
        objective = []
        for index_lo in self.dict_linked_orders:
            delta_p = self.model.get_variable(constants.delta_p_lo(index_lo))
            objective.append(self.parameters.paradoxically_accepted_penalty * delta_p)
        return self.model.add_objective(sum(objective))

    def create_paradoxical_pc_objective(self, opposite_delta_p_dict: dict[int, float | None]):
        objective = []
        for index_pc in self.dict_parent_child_orders:
            if opposite_delta_p_dict[index_pc] is not None:
                delta_p = self.model.get_variable(constants.delta_p_pc(index_pc))
                objective.append(self.parameters.paradoxically_accepted_penalty * delta_p)
        return self.model.add_objective(sum(objective))

    def create_paradoxical_order_objective(self):
        objective = []
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.name not in self._full_link_id_by_order and mc_order.parent_child_id is None:
                if mc_order.requires_status_variable is None or mc_order.parent_child_id is not None:
                    continue
                time_index = mc_order.time_index
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]

                if local_cleared_power > self.parameters.allowed_round_off_error:
                    delta_p = self.model.get_variable(
                        constants.delta_p_order(mc_order.name, mc_order.market_area.name, time_index)
                    )
                    objective.append(self.parameters.paradoxically_accepted_penalty * delta_p)
        return self.model.add_objective(sum(objective))

    def create_paradoxical_delta_price_pc_constraints(self, opposite_delta_p_dict: dict[int, float | None]):
        for index_pc in self.dict_parent_child_orders:
            if opposite_delta_p_dict[index_pc] is not None:
                paradoxical_delta_p = self.model.get_variable(constants.delta_p_pc(index_pc))
                self.model.add_constraint(
                    paradoxical_delta_p >= opposite_delta_p_dict[index_pc],
                    constants.paradoxical_delta_p_pc_constraint_name(index_pc),
                )

    def create_paradoxical_delta_price_lo_constraints(self):
        for index_lo, orders in self.dict_linked_orders.items():
            paradoxical_delta_p = self.model.get_variable(constants.delta_p_lo(index_lo))
            opposite_delta_p = 0
            for order in orders:
                mc_order = self.input_dataset.mc_orders[order.name]
                time_index = mc_order.time_index
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]
                local_price = self.model.get_variable(
                    constants.price_on_group_variable_name(mc_order.group_index, time_index)
                )
                coeff_sale = mc_order.production_sign

                # If order is accepted, add its delta P to the overall paradoxical delta P of this group of linked orders
                if local_cleared_power > self.parameters.allowed_round_off_error:
                    opposite_delta_p += coeff_sale * (mc_order.price - local_price)

            self.model.add_constraint(
                paradoxical_delta_p >= opposite_delta_p, constants.paradoxical_delta_p_lo_constraint_name(index_lo)
            )

    # Generator of border ranks and names of neighbour area for each border of a given market area:
    def get_market_area_neighbours(self, mc_market_area_name: str) -> list[tuple[MarketBorderMC, str]]:
        neighbours_area = []
        for mc_border in self.input_dataset.mc_market_borders.values():
            neighbour_area = (
                mc_border.downhill_market_area
                if mc_border.uphill_market_area.name == mc_market_area_name
                else mc_border.uphill_market_area
            )
            neighbours_area.append((mc_border, neighbour_area.name))
        return neighbours_area

    # Append all neighbour areas recursively as long as they are not already part of the group and the connection is not
    # saturated:
    def propagate_through_unsaturated(
        self,
        mc_market_area: MarketAreaMC,
        time_index: int,
        area_price_group: dict[str, int | None],
        price_group: PriceGroup,
    ):
        for mc_border, neighbour_market_area_name in self.get_market_area_neighbours(mc_market_area.name):
            if neighbour_market_area_name in price_group.market_area_names:
                continue
            flow = self.clearing_border_exchanges[mc_border.name, time_index]
            time = self.input_dataset.times[time_index]
            relative_max_flow = mc_border.max_flow.get_value(time)
            relative_min_flow = mc_border.min_flow.get_value(time)
            if (
                relative_min_flow + self.parameters.allowed_round_off_error
                <= flow
                <= relative_max_flow - self.parameters.allowed_round_off_error
            ):
                area_price_group[neighbour_market_area_name] = price_group.id
                price_group.market_area_names.append(neighbour_market_area_name)
                neighbour_market_area = self.input_dataset.mc_market_areas[neighbour_market_area_name]
                self.propagate_through_unsaturated(neighbour_market_area, time_index, area_price_group, price_group)

    def create_price_groups(self) -> dict[int, list[PriceGroup]]:
        price_groups: dict[int, list[PriceGroup]] = {}
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups[time_index] = []
            if self.input_dataset.is_atc:
                # Initialize a dict linking each market area with a price group number:
                areas_price_group: dict[str, int | None] = {}
                for market_area_name in self.input_dataset.mc_market_areas:
                    areas_price_group[market_area_name] = None

                for group_id, (market_area_name, mc_market_area) in enumerate(
                    self.input_dataset.mc_market_areas.items()
                ):
                    # If the current area is already allocated to a price group, go to the next one:
                    if areas_price_group[market_area_name] is not None:
                        continue
                    price_group = PriceGroup(group_id, time_index)
                    price_group.market_area_names.append(market_area_name)
                    areas_price_group[market_area_name] = group_id
                    price_groups[time_index].append(price_group)

                    # Loop over borders that are not saturated and link all possible areas inside the current group in a
                    # recursive way:
                    self.propagate_through_unsaturated(mc_market_area, time_index, areas_price_group, price_group)
            else:
                if (
                    count_saturated(self.saturated_critical_branch, time_index, self.parameters.allowed_round_off_error)
                    == 0
                ):
                    unique_price_group = PriceGroup(0, time_index)
                    unique_price_group.market_area_names = list(self.input_dataset.mc_market_areas)
                    price_groups[time_index].append(unique_price_group)
                else:
                    for group_id, market_area_name in enumerate(self.input_dataset.mc_market_areas):
                        new_price_group = PriceGroup(group_id, time_index)
                        new_price_group.market_area_names = [market_area_name]
                        price_groups[time_index].append(new_price_group)
        for price_group_list in price_groups.values():
            for price_group in price_group_list:
                self.compute_price_bounds(price_group, 1)
        return price_groups

    def is_neighbour(self, price_group: PriceGroup, other_price_group: PriceGroup) -> bool:
        """Check if two group are neighbour

        :param price_group: PriceGroup.
        :param other_price_group: PriceGroup. The PriceGroup to check
        :return: bool. True if there are neighbour otherwise False
        """
        # Count the number of occurrences of each market border inside the
        # current group (self):
        current_borders_counts = {}
        for border_name, mc_market_border in self.input_dataset.mc_market_borders.items():
            for market_area_name in price_group.market_area_names:
                if (
                    market_area_name == mc_market_border.uphill_market_area.name
                    or market_area_name == mc_market_border.downhill_market_area.name
                ):
                    if border_name not in current_borders_counts:
                        current_borders_counts[border_name] = 0
                    current_borders_counts[border_name] += 1

        # Deduce the list of borders that appear only once, as they define the external border of the group:
        current_external_borders = [
            border_name for border_name, border_count in current_borders_counts.items() if border_count == 1
        ]

        # Count the number of occurrences of each market border inside the
        # other group (self):
        other_borders_counts = {}
        for border_name, mc_market_border in self.input_dataset.mc_market_borders.items():
            for market_area_name in other_price_group.market_area_names:
                if (
                    market_area_name == mc_market_border.uphill_market_area.name
                    or market_area_name == mc_market_border.downhill_market_area.name
                ):
                    if border_name not in other_borders_counts:
                        other_borders_counts[border_name] = 0
                    other_borders_counts[border_name] += 1

        # Deduce the list of borders that appear only once, as they define the external border of the group:
        other_external_borders = [
            border_name for border_name, border_count in other_borders_counts.items() if border_count == 1
        ]

        # Check if there is at least one common external border between both
        # groups. If so, they are neighbours, otherwise they are not:
        for other_border_name in other_external_borders:
            if other_border_name in current_external_borders:
                return True
        return False

    def compute_price_bounds(self, price_group: PriceGroup, pricing_type: int):
        for market_area_name in price_group.market_area_names:
            time = self.input_dataset.times[price_group.time_index]
            mc_market_area = self.input_dataset.mc_market_areas[market_area_name]
            # Initialize the local bounds on order prices:
            max_accepted_sale_price = max_rejected_purchase_price = mc_market_area.min_price.get_value(time)
            min_rejected_sale_price = min_accepted_purchase_price = mc_market_area.max_price.get_value(time)

            # Select orders involved during the current time step (generator):
            current_orders = (
                mc_order
                for mc_order in mc_market_area.mc_orders.values()
                if mc_order.start_date <= time < mc_order.end_date
            )

            for mc_order in current_orders:
                current_power = self.clearing_accepted_powers[market_area_name, mc_order.name]
                # Skip complex orders to compute price bounds
                # Linked order
                if mc_order.is_linked:
                    continue

                    # Other complex order
                if mc_order.requires_status_variable is not None:
                    continue

                    # Combined accepted at their min:
                if (abs(current_power - mc_order.qmin) <= self.parameters.allowed_round_off_error) and (
                    mc_order.qmin != 0.0
                ):
                    continue

                # Compute the relevant bound:
                if mc_order.is_sale:
                    if abs(current_power) >= self.parameters.allowed_round_off_error:
                        max_accepted_sale_price = max(max_accepted_sale_price, mc_order.price)
                    else:
                        min_rejected_sale_price = min(min_rejected_sale_price, mc_order.price)
                else:
                    if abs(current_power) >= self.parameters.allowed_round_off_error:
                        min_accepted_purchase_price = min(min_accepted_purchase_price, mc_order.price)
                    else:
                        max_rejected_purchase_price = max(max_rejected_purchase_price, mc_order.price)

                # Once done with orders, deduce the bounds on the group price:
                # In the first pricing, these bounds are computed taking into account both accepted and rejected orders
            if pricing_type == 1:
                price_group.min_price = max(price_group.min_price, max_accepted_sale_price, max_rejected_purchase_price)
                price_group.max_price = min(price_group.max_price, min_rejected_sale_price, min_accepted_purchase_price)
                # In the second, rejected orders are not taken into account to compute the price bounds
            else:
                price_group.min_price = max(price_group.min_price, max_accepted_sale_price)
                price_group.max_price = min(price_group.max_price, min_accepted_purchase_price)

    # Surplus constraints
    # Utils
    # Finds the price group of a given order and fills its attribute
    def instantiate_order_group_index(self):
        for price_group_list in self.price_groups.values():
            for price_group in price_group_list:
                for market_area_name in price_group.market_area_names:
                    for mc_order in self.input_dataset.mc_market_areas[market_area_name].mc_orders.values():
                        if mc_order.time_index == price_group.time_index:
                            mc_order.group_index = price_group.id

    def update_price_bound(self):
        for price_group_list in self.price_groups.values():
            for price_group in price_group_list:
                price_group.max_price = float("inf")
                price_group.min_price = -float("inf")
                self.compute_price_bounds(price_group, 2)
                logger.debug(
                    f"Updating price variables for group {(price_group.time_index, price_group.id)} with bounds "
                    f"{price_group.min_price} and {price_group.max_price}"
                )
                price_group_variable = self.model.get_variable(
                    constants.price_on_group_variable_name(price_group.id, price_group.time_index)
                )
                price_group_variable.SetLb(price_group.min_price)
                price_group_variable.SetUb(price_group.max_price)

    def compute_min_max_rejected_sale_buy(self):
        for time_index, price_groups in self.price_groups.items():
            for price_group in price_groups:
                price_group.min_rejected_sale = float("inf")
                price_group.max_rejected_buy = -float("inf")
                for market_area_name in price_group.market_area_names:
                    mc_market_area = self.input_dataset.mc_market_areas[market_area_name]

                    for mc_order in mc_market_area.mc_orders.values():
                        # Keep only orders in correct time
                        if mc_order.time_index != time_index:
                            continue
                        local_acc_power = self.clearing_accepted_powers[market_area_name, mc_order.name]
                        # Keep only rejected orders
                        if abs(mc_order.qmax - local_acc_power) > self.parameters.allowed_round_off_error:
                            if mc_order.is_sale:
                                price_group.min_rejected_sale = min(mc_order.price, price_group.min_rejected_sale)
                            else:
                                price_group.max_rejected_buy = max(mc_order.price, price_group.max_rejected_buy)
                logger.debug(f"Worst rejected : {price_group.min_rejected_sale}, {price_group.max_rejected_buy}")

    def get_market_prices(self) -> dict[tuple[str, int], float]:
        """
        :rtype: dict[tuple[str, int], float]
        """
        market_prices = {}
        for time_index, price_groups in self.price_groups.items():
            for price_group in price_groups:
                for market_area_name in price_group.market_area_names:
                    market_price_name = constants.price_on_group_variable_name(price_group.id, time_index)
                    market_prices[market_area_name, time_index] = self.model.get_variable(
                        market_price_name
                    ).solution_value()
        return market_prices
