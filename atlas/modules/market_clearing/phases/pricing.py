"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import json

import pendulum

import atlas.modules.market_clearing.constants as constants
from atlas.config import logger
from atlas.enums import ComplementDirection, CouplingType, SolverStatus
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_area import MarketAreaMC
from atlas.modules.market_clearing.input_objects.market_border import MarketBorderMC
from atlas.modules.market_clearing.input_objects.order_coupling import OrderCouplingMC
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.price_group import PriceGroup
from atlas.objects.market.order import Order
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel


class Pricing(OptimisationModel):
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

        super().__init__(parameters.solver.solver_name, options=solver_options, name="Pricing")
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.saturated_critical_branch = saturated_critical_branch
        self.clearing_border_exchanges = exchange_fixing_border_exchanges
        self.clearing_local_balances = clearing_local_balances
        self.clearing_accepted_powers = clearing_accepted_powers
        self.price_groups = self.create_price_groups()
        self.dict_circular_children_bids = self.get_circular_parent_child_sets()
        self.dict_linked_orders = self.compute_linked_bids_sets()
        self.dict_parent_child_orders = self.compute_parent_child_sets()

    def compute(self):
        self.build_first()
        solver_info = self.solve()
        output_path = self.parameters.get_lp_dir()
        if self.parameters.solver.export_lp:
            output_path.mkdir(parents=True, exist_ok=True)
            self.export_model(str(output_path / "pricing_1_model.lp"))
        if solver_info.status not in [SolverStatus.OPTIMAL, SolverStatus.FEASIBLE]:
            self.build_second()
            solver_info = self.solve()
            if self.parameters.solver.export_lp:
                self.export_model(str(output_path / "pricing_2_model.lp"))

        if solver_info.status not in [SolverStatus.OPTIMAL, SolverStatus.FEASIBLE]:
            self.build_third()
            _ = self.solve()
            if self.parameters.solver.export_lp:
                self.export_model(str(output_path / "pricing_3_model.lp"))
        if self.parameters.solver.export_lp:
            with open(output_path / "pricing_market_prices.json", "w") as f:
                json.dump(
                    [
                        [market_area_name, time_index, val]
                        for (market_area_name, time_index), val in self.retrieve_market_prices().items()
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
        self.set_direction("minimize")
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
        opposite_delta_p_dict = self.create_opposite_delta_p()
        self.build_third_variables(opposite_delta_p_dict)
        self.build_third_constraints(opposite_delta_p_dict)
        self.build_third_objective(opposite_delta_p_dict)

    def build_third_variables(self, opposite_delta_p_dict: dict[int, float]):
        """Create all variables for the third pricing phase model"""
        self.create_delta_price_lo_variables()
        self.create_delta_price_pc_variables(opposite_delta_p_dict)
        self.create_delta_price_order_variables()

    def build_third_constraints(self, opposite_delta_p_dict: dict[int, float]):
        """Create all constraints for the third pricing phase model"""
        self.deactivate_positive_surplus_lo_constraints()
        self.deactivate_negative_surplus_pc_constraints()
        self.deactivate_positive_surplus_pc_constraints()
        self.deactivate_positive_surplus_order_constraints()
        self.create_paradoxical_delta_price_lo_constraints()
        self.create_paradoxical_delta_price_pc_constraints(opposite_delta_p_dict)
        self.create_paradoxical_delta_price_order_constraints()

    def build_third_objective(self, opposite_delta_p_dict: dict[int, float]):
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
                    self.add_continuous_variable(constants.link_child_to_pc(index_child, index_pc), 0, float("inf"))
                    index_child += 1

    def create_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                self.add_continuous_variable(
                    constants.price_on_group_variable_name(price_group.id, time_index),
                    -float("inf"),
                    float("inf"),
                )

    def create_positive_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                self.add_continuous_variable(
                    constants.positive_price_on_group_variable_name(price_group.id, time_index),
                    0.0,
                    float("inf"),
                )

    def create_negative_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                self.add_continuous_variable(
                    constants.negative_price_on_group_variable_name(price_group.id, time_index),
                    -float("inf"),
                    0.0,
                )

    def create_positive_diff_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            for i in range(len(price_groups) - 1):
                for j in range(i + 1, len(price_groups)):
                    self.add_continuous_variable(
                        constants.positive_price_diff_on_group_variable_name(
                            price_groups[i].id, price_groups[j].id, time_index
                        ),
                        0.0,
                        float("inf"),
                    )

    def create_negative_diff_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            for i in range(len(price_groups) - 1):
                for j in range(i + 1, len(price_groups)):
                    self.add_continuous_variable(
                        constants.negative_price_diff_on_group_variable_name(
                            price_groups[i].id, price_groups[j].id, time_index
                        ),
                        -float("inf"),
                        0.0,
                    )

    def create_shadow_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for critical_branch_name in self.input_dataset.mc_critical_branches:
                self.add_continuous_variable(
                    constants.shadow_price_variable_name(critical_branch_name, time_index),
                    -float("inf"),
                    0.0,
                )

    def create_positive_slack_branch_load_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            nb_saturated = len(
                [
                    1
                    for (_, cb_time_index), value in self.saturated_critical_branch.items()
                    if abs(value) <= self.parameters.allowed_round_off_error and cb_time_index == time_index
                ]
            )
            if nb_saturated != 0:
                continue
            for i in range(len(price_groups) - 1):
                for j in range(i + 1, len(price_groups)):
                    self.add_continuous_variable(
                        constants.positive_slack_branch_load_constraint_name(
                            price_groups[i].id, price_groups[j].id, time_index
                        ),
                        0.0,
                        float("inf"),
                    )

    def create_negative_slack_branch_load_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            nb_saturated = len(
                [
                    1
                    for (_, cb_time_index), value in self.saturated_critical_branch.items()
                    if abs(value) <= self.parameters.allowed_round_off_error and cb_time_index == time_index
                ]
            )
            if nb_saturated != 0:
                continue
            for i in range(len(price_groups) - 1):
                for j in range(i + 1, len(price_groups)):
                    self.add_continuous_variable(
                        constants.negative_slack_branch_load_constraint_name(
                            price_groups[i].id, price_groups[j].id, time_index
                        ),
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
                local_price = self.get_variable(
                    constants.price_on_group_variable_name(mc_order.group_index, time_index)
                )
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]
                coeff_sale = 1 if mc_order.is_sale else -1

                # If order is accepted, add its surplus to the overall surplus of this group of linked orders
                if local_cleared_power > self.parameters.allowed_round_off_error:
                    surplus += coeff_sale * local_cleared_power * (local_price - mc_order.price)

            self.add_constraint(
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

                local_price = self.get_variable(
                    constants.price_on_group_variable_name(child_mc_order.group_index, time_index)
                )
                local_cleared_power = self.clearing_accepted_powers[
                    child_mc_order.market_area.name, child_mc_order.name
                ]
                coeff_sale = 1 if child_mc_order.is_sale else -1

                if local_cleared_power > self.parameters.allowed_round_off_error:
                    link_surplus = self.get_variable(constants.link_child_to_pc(index_child, index_pc))
                    sum_children_link_surplus += link_surplus
                    logger.debug(f"surplus child {index_child} PC {index_pc}")
                    self.add_constraint(
                        (coeff_sale * local_cleared_power * (local_price - child_mc_order.price) - link_surplus) >= 0.0,
                        constants.positive_parent_child_surplus_constraint_name(index_child, index_pc, time_index),
                    )
                    index_child += 1

            # Then set global constraint on parents
            surplus = 0
            for parent_order in parent_orders:
                parent_mc_order = self.input_dataset.mc_orders[parent_order.name]
                time_index = parent_mc_order.time_index

                local_price = self.get_variable(
                    constants.price_on_group_variable_name(parent_mc_order.group_index, time_index)
                )
                local_cleared_power = self.clearing_accepted_powers[
                    parent_mc_order.market_area.name, parent_mc_order.name
                ]
                coeff_sale = 1 if parent_mc_order.is_sale else -1

                # If order is accepted, add its surplus to the overall surplus of this group of linked orders
                if local_cleared_power > self.parameters.allowed_round_off_error:
                    surplus += coeff_sale * local_cleared_power * (local_price - parent_order.price)
            logger.debug(f"Surplus parent PC {index_pc}")
            if surplus:
                self.add_constraint(
                    surplus + sum_children_link_surplus >= 0.0,
                    constants.negative_parent_child_surplus_constraint_name(index_pc),
                )

    def create_pos_surplus_order_constraints(self):
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.full_link_id is None and mc_order.parent_child_id is None:
                time_index = mc_order.time_index

                local_price = self.get_variable(
                    constants.price_on_group_variable_name(mc_order.group_index, time_index)
                )
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]

                if local_cleared_power > self.parameters.allowed_round_off_error:
                    coeff_sale = 1 if mc_order.is_sale else -1
                    equipment_name = mc_order.equipment.name if mc_order.equipment else "NA"
                    self.add_constraint(
                        coeff_sale * local_cleared_power * (local_price - mc_order.price) >= 0.0,
                        constants.pos_surplus_order_constraint_name(
                            mc_order.name, equipment_name, mc_order.market_area.name, time_index
                        ),
                    )

    def create_null_marginal_order_constraints(self):
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.full_link_id is None and mc_order.parent_child_id is None:
                time_index = mc_order.time_index

                local_price = self.get_variable(
                    constants.price_on_group_variable_name(mc_order.group_index, time_index)
                )
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]

                if local_cleared_power > self.parameters.allowed_round_off_error:
                    coeff_sale = 1 if mc_order.is_sale else -1
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
                            self.add_constraint(
                                coeff_sale * local_cleared_power * (local_price - mc_order.price) == 0.0,
                                constraint_name,
                            )

    def create_shadow_price_constraints(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for critical_branch_name in self.input_dataset.mc_critical_branches:
                shadow_price = self.get_variable(constants.shadow_price_variable_name(critical_branch_name, time_index))
                saturated_critical_branch = self.saturated_critical_branch[critical_branch_name, time_index]
                if saturated_critical_branch > 0.01:
                    self.add_constraint(
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
                        price_in = self.get_variable(constants.price_on_group_variable_name(price_group.id, time_index))
                    if mc_border.downhill_market_area.name in price_group.market_area_names:
                        price_out = self.get_variable(
                            constants.price_on_group_variable_name(price_group.id, time_index)
                        )

                if price_in and not price_out:
                    self.add_constraint(
                        -border_exchange * price_in >= 0.0,
                        constants.adverse_flow_constraint_name(border_name, time_index),
                    )
                elif price_out and not price_in:
                    self.add_constraint(
                        border_exchange * price_out >= 0.0,
                        constants.adverse_flow_constraint_name(border_name, time_index),
                    )

    def create_absolute_price_group_constraint(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                positive_price = self.get_variable(
                    constants.positive_price_on_group_variable_name(price_group.id, time_index)
                )
                negative_price = self.get_variable(
                    constants.negative_price_on_group_variable_name(price_group.id, time_index)
                )
                price = self.get_variable(constants.price_on_group_variable_name(price_group.id, time_index))
                self.add_constraint(
                    positive_price + negative_price - price == 0.0,
                    constants.absolute_price_group_constraint_name(price_group.id, _time),
                )
        return

    def create_branch_load_constraint(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            nb_saturated = len(
                [
                    1
                    for (_, cb_time_index), value in self.saturated_critical_branch.items()
                    if abs(value) <= self.parameters.allowed_round_off_error and cb_time_index == time_index
                ]
            )
            if nb_saturated != 0:
                continue
            for i in range(len(price_groups) - 1):
                for j in range(i + 1, len(price_groups)):
                    price = self.get_variable(constants.price_on_group_variable_name(price_groups[i].id, time_index))
                    other_price = self.get_variable(
                        constants.price_on_group_variable_name(price_groups[j].id, time_index)
                    )
                    branch_load = price - other_price
                    if self.parameters.fb_branch_load_slack_penalty:
                        positive_slack = self.get_variable(
                            constants.negative_slack_branch_load_constraint_name(
                                price_groups[i].id, price_groups[j].id, time_index
                            )
                        )
                        negative_slack = self.get_variable(
                            constants.negative_slack_branch_load_constraint_name(
                                price_groups[i].id, price_groups[j].id, time_index
                            )
                        )
                        branch_load += positive_slack + negative_slack
                    for critical_branch_name, mc_critical_branch in self.input_dataset.mc_critical_branches.items():
                        for market_area_name in self.input_dataset.mc_market_areas:
                            if market_area_name in price_groups[i].market_area_names:
                                coeff = 1.0
                            elif market_area_name in price_groups[j].market_area_names:
                                coeff = -1.0
                            else:
                                continue

                            if market_area_name in mc_critical_branch.ptdf:
                                branch_ptdf = mc_critical_branch.ptdf[market_area_name]
                                shadow_prices_fb = self.get_variable(
                                    constants.shadow_price_variable_name(critical_branch_name, time_index)
                                )
                                branch_load += (
                                    coeff
                                    * branch_ptdf.get_value(self.convert_time_index_to_time(time_index))
                                    * shadow_prices_fb
                                )

                    self.add_constraint(
                        branch_load == 0.0,
                        constants.price_ptdf_constraint_name(price_groups[i].id, price_groups[j].id, time_index),
                    )

    def create_add_price_difference_constraint(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            for i in range(len(price_groups) - 1):
                for j in range(i + 1, len(price_groups)):
                    if not self.is_neighbour(price_groups[i], price_groups[j]):
                        continue
                    price = self.get_variable(constants.price_on_group_variable_name(price_groups[i].id, time_index))
                    other_price = self.get_variable(
                        constants.price_on_group_variable_name(price_groups[j].id, time_index)
                    )
                    positive_price_diff = self.get_variable(
                        constants.positive_price_diff_on_group_variable_name(
                            price_groups[i].id, price_groups[j].id, time_index
                        )
                    )
                    negative_price_diff = self.get_variable(
                        constants.negative_price_diff_on_group_variable_name(
                            price_groups[i].id, price_groups[j].id, time_index
                        )
                    )

                    self.add_constraint(
                        positive_price_diff + negative_price_diff == price - other_price,
                        constants.price_difference_constraint_name(price_groups[i].id, price_groups[j].id, _time),
                    )

    def create_groups_prices_objective(self):
        objective = []
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                price = self.get_variable(constants.price_on_group_variable_name(price_group.id, time_index))
                objective.append(self.parameters.market_price_penalty_alpha * price)
        return self.add_objective(sum(objective))

    def create_absolute_price_objective(self):
        objective = []
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                positive_price = self.get_variable(
                    constants.positive_price_on_group_variable_name(price_group.id, time_index)
                )
                negative_price = self.get_variable(
                    constants.negative_price_on_group_variable_name(price_group.id, time_index)
                )
                objective.append(self.parameters.market_price_penalty_beta * (positive_price - negative_price))
        return self.add_objective(sum(objective))

    def create_branch_load_objective(self):
        objective = []
        for time_index, _time in enumerate(self.input_dataset.times):
            nb_saturated = len(
                [
                    1
                    for (_, cb_time_index), value in self.saturated_critical_branch.items()
                    if abs(value) <= self.parameters.allowed_round_off_error and cb_time_index == time_index
                ]
            )
            if nb_saturated != 0:
                continue
            price_groups = self.price_groups[time_index]
            for i in range(len(price_groups) - 1):
                for j in range(i + 1, len(price_groups)):
                    positive_load_slack = self.get_variable(
                        constants.positive_slack_branch_load_constraint_name(
                            price_groups[i].id, price_groups[j].id, time_index
                        )
                    )
                    negative_load_slack = self.get_variable(
                        constants.negative_slack_branch_load_constraint_name(
                            price_groups[i].id, price_groups[j].id, time_index
                        )
                    )
                    objective.append(
                        self.parameters.fb_branch_load_slack_penalty * (positive_load_slack - negative_load_slack)
                    )
        return self.add_objective(sum(objective))

    def create_groups_price_diff_objective(self):
        objective = []
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            for i in range(len(price_groups) - 1):
                for j in range(i + 1, len(price_groups)):
                    if not self.is_neighbour(price_groups[i], price_groups[j]):
                        continue
                    positive_price_diff = self.get_variable(
                        constants.positive_price_diff_on_group_variable_name(
                            price_groups[i].id, price_groups[j].id, time_index
                        )
                    )
                    negative_price_diff = self.get_variable(
                        constants.negative_price_diff_on_group_variable_name(
                            price_groups[i].id, price_groups[j].id, time_index
                        )
                    )
                    objective.append(
                        self.parameters.fb_branch_load_slack_penalty * (positive_price_diff - negative_price_diff)
                    )
        return self.add_objective(sum(objective))

    # Second Pricing variables
    def create_surplus_rejected_variables(self):
        for price_group_list in self.price_groups.values():
            for price_group in price_group_list:
                self.add_continuous_variable(
                    constants.worst_rej_sale_group(price_group.id, price_group.time_index),
                    0.0,
                    float("inf"),
                )
                self.add_continuous_variable(
                    constants.worst_rej_buy_group(price_group.id, price_group.time_index),
                    0.0,
                    float("inf"),
                )

    def deactivate_null_marginal_order_constraint(self):
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.full_link_id is None and mc_order.parent_child_id is None:
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
                            self.deactivate_constraint(constraint_name)

    def create_min_surplus_rejected_sale_constraints(self):
        for time_index, price_groups in self.price_groups.items():
            for price_group in price_groups:
                current_price = self.get_variable(constants.price_on_group_variable_name(price_group.id, time_index))

                logger.debug(f"New bounds : {current_price.lb()}, {current_price.ub()}")
                min_rejected_sale = self.get_variable(constants.worst_rej_sale_group(price_group.id, time_index))
                self.add_constraint(
                    min_rejected_sale - (current_price - price_group.min_rejected_sale) >= 0.0,
                    constants.pos_min_rej_sale_group_constraint_name(price_group.id, time_index),
                )

    def create_max_surplus_rejected_buy_constraints(self):
        for time_index, price_groups in self.price_groups.items():
            for price_group in price_groups:
                current_price = self.get_variable(constants.price_on_group_variable_name(price_group.id, time_index))

                logger.debug(f"New bounds : {current_price.lb()}, {current_price.ub()}")
                max_rejected_buy = self.get_variable(constants.worst_rej_buy_group(price_group.id, time_index))
                self.add_constraint(
                    max_rejected_buy - (price_group.max_rejected_buy - current_price) >= 0.0,
                    constants.pos_max_rej_buy_group_constraint_name(price_group.id, time_index),
                )

    def create_surplus_objective(self):
        objective = []
        for price_groups in self.price_groups.values():
            for price_group in price_groups:
                max_rejected_buy = self.get_variable(
                    constants.worst_rej_buy_group(price_group.id, price_group.time_index)
                )
                min_rejected_sale = self.get_variable(
                    constants.worst_rej_sale_group(price_group.id, price_group.time_index)
                )
                objective.append(
                    self.parameters.paradoxically_rejected_penalty_N * (min_rejected_sale + max_rejected_buy)
                )
        return self.add_objective(sum(objective))

    # Pricing 3
    def create_opposite_delta_p(self) -> dict[int, float]:
        opposite_delta_p_dict = {}
        for index_pc, (parent_orders, children_orders) in self.dict_parent_child_orders.items():
            opposite_delta_p = 0.0
            for order in parent_orders + children_orders:
                mc_order = self.input_dataset.mc_orders[order.name]
                time_index = mc_order.time_index
                if time_index is None or mc_order.group_index is None:
                    continue
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]
                local_price = self.get_variable(
                    constants.price_on_group_variable_name(mc_order.group_index, time_index)
                )
                coeff_sale = 1 if mc_order.is_sale else -1

                # If order is accepted, add its delta P to the overall paradoxical delta P of this group of linked orders
                if local_cleared_power > self.parameters.allowed_round_off_error:
                    opposite_delta_p += coeff_sale * (mc_order.price - local_price)
            opposite_delta_p_dict[index_pc] = opposite_delta_p
        return opposite_delta_p_dict

    def create_delta_price_lo_variables(self):
        for index_lo in self.dict_linked_orders:
            self.add_continuous_variable(constants.delta_p_lo(index_lo), 0, float("inf"))

    def create_delta_price_pc_variables(self, opposite_delta_p_dict: dict[int, float]):
        for index_pc in self.dict_parent_child_orders:
            if not isinstance(opposite_delta_p_dict[index_pc], int):
                self.add_continuous_variable(constants.delta_p_pc(index_pc), 0, float("inf"))

    def create_delta_price_order_variables(self):
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.full_link_id is None and mc_order.parent_child_id is None:
                if mc_order.id_with_status is None or mc_order.parent_child_id is not None:
                    continue
                time_index = mc_order.time_index
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]

                if local_cleared_power > self.parameters.allowed_round_off_error:
                    self.add_continuous_variable(
                        constants.delta_p_order(mc_order.name, mc_order.market_area.name, time_index), 0, float("inf")
                    )

    def deactivate_positive_surplus_lo_constraints(self):
        for index_lo in self.dict_linked_orders:
            constraint_name = constants.linked_bids_surplus_constraint_name(index_lo)
            if constraint_name:
                self.deactivate_constraint(constraint_name)

    def deactivate_negative_surplus_pc_constraints(self):
        for index_pc in self.dict_parent_child_orders:
            constraint_name = constants.negative_parent_child_surplus_constraint_name(index_pc)
            if constraint_name:
                # If there is surplus
                if constraint_name in self.constraints:
                    self.deactivate_constraint(constraint_name)
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
                    self.deactivate_constraint(constraint_name)
                    index_child += 1

    def deactivate_positive_surplus_order_constraints(self):
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.full_link_id is None and mc_order.parent_child_id is None:
                if mc_order.id_with_status is not None and mc_order.parent_child_id is None:
                    local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]

                    if local_cleared_power > self.parameters.allowed_round_off_error:
                        equipment_name = mc_order.equipment.name if mc_order.equipment else "NA"
                        constraint_name = constants.pos_surplus_order_constraint_name(
                            mc_order.name, equipment_name, mc_order.market_area.name, mc_order.time_index
                        )
                        if constraint_name:
                            self.deactivate_constraint(constraint_name)

    def create_paradoxical_delta_price_order_constraints(self):
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.full_link_id is None and mc_order.parent_child_id is None:
                if mc_order.id_with_status is not None and mc_order.parent_child_id is None:
                    local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]
                    if local_cleared_power > self.parameters.allowed_round_off_error:
                        time_index = mc_order.time_index
                        local_price = self.get_variable(
                            constants.price_on_group_variable_name(mc_order.group_index, time_index)
                        )
                        coeff_sale = 1 if mc_order.is_sale else -1
                        opposite_delta_p = coeff_sale * (mc_order.price - local_price)
                        paradoxical_delta_p = self.get_variable(
                            constants.delta_p_order(mc_order.name, mc_order.market_area.name, time_index)
                        )
                        self.add_constraint(
                            paradoxical_delta_p >= opposite_delta_p,
                            constants.paradoxical_delta_p_order_constraint_name(
                                mc_order.name, mc_order.market_area.name, time_index
                            ),
                        )

    def create_paradoxical_lo_objective(self):
        objective = []
        for index_lo in self.dict_linked_orders:
            delta_p = self.get_variable(constants.delta_p_lo(index_lo))
            objective.append(self.parameters.paradoxically_accepted_penalty_M * delta_p)
        return self.add_objective(sum(objective))

    def create_paradoxical_pc_objective(self, opposite_delta_p_dict: dict[int, float]):
        objective = []
        for index_pc in self.dict_parent_child_orders:
            if not isinstance(opposite_delta_p_dict[index_pc], int):
                delta_p = self.get_variable(constants.delta_p_pc(index_pc))
                objective.append(self.parameters.paradoxically_accepted_penalty_M * delta_p)
        return self.add_objective(sum(objective))

    def create_paradoxical_order_objective(self):
        objective = []
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.full_link_id is None and mc_order.parent_child_id is None:
                if mc_order.id_with_status is None or mc_order.parent_child_id is not None:
                    continue
                time_index = mc_order.time_index
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]

                if local_cleared_power > self.parameters.allowed_round_off_error:
                    delta_p = self.get_variable(
                        constants.delta_p_order(mc_order.name, mc_order.market_area.name, time_index)
                    )
                    objective.append(self.parameters.paradoxically_accepted_penalty_M * delta_p)
        return self.add_objective(sum(objective))

    def create_paradoxical_delta_price_pc_constraints(self, opposite_delta_p_dict: dict[int, float]):
        for index_pc in self.dict_parent_child_orders:
            if not isinstance(opposite_delta_p_dict[index_pc], int):
                paradoxical_delta_p = self.get_variable(constants.delta_p_pc(index_pc))
                self.add_constraint(
                    paradoxical_delta_p >= opposite_delta_p_dict[index_pc],
                    constants.paradoxical_delta_p_pc_constraint_name(index_pc),
                )

    def create_paradoxical_delta_price_lo_constraints(self):
        for index_lo, orders in self.dict_linked_orders.items():
            paradoxical_delta_p = self.get_variable(constants.delta_p_lo(index_lo))
            opposite_delta_p = 0
            for order in orders:
                mc_order = self.input_dataset.mc_orders[order.name]
                time_index = mc_order.time_index
                local_cleared_power = self.clearing_accepted_powers[mc_order.market_area.name, mc_order.name]
                local_price = self.get_variable(
                    constants.price_on_group_variable_name(mc_order.group_index, time_index)
                )
                coeff_sale = 1 if mc_order.is_sale else -1

                # If order is accepted, add its delta P to the overall paradoxical delta P of this group of linked orders
                if local_cleared_power > self.parameters.allowed_round_off_error:
                    opposite_delta_p += coeff_sale * (mc_order.price - local_price)

            self.add_constraint(
                paradoxical_delta_p >= opposite_delta_p, constants.paradoxical_delta_p_lo_constraint_name(index_lo)
            )

    def convert_time_index_to_time(self, time_index: int) -> pendulum.DateTime:
        return self.parameters.temporal.start_date + time_index * self.parameters.temporal.timestep

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
            relative_max_flow = mc_border.max_flow.get_value(self.convert_time_index_to_time(time_index))
            relative_min_flow = mc_border.min_flow.get_value(self.convert_time_index_to_time(time_index))
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
                nb_saturated = len(
                    [
                        1
                        for (_, cb_time_index), value in self.saturated_critical_branch.items()
                        if abs(value) <= self.parameters.allowed_round_off_error and cb_time_index == time_index
                    ]
                )
                if nb_saturated == 0:
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
            time = self.convert_time_index_to_time(price_group.time_index)
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
                if mc_order.id_with_status is not None:
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

    # Defines the global circular parent_child sets and stores them in a dictionary
    def get_circular_parent_child_sets(self):
        dict_circular_children_bids = {}
        index_pc_t = 0

        # Step 1 - Filling the dictionary with unique circular PC linked sets
        for mc_order_coupling in self.input_dataset.mc_order_couplings.values():
            if mc_order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                list_children = [mc_order_coupling.orders[0]]
                circular_orders = self.get_circular_children(mc_order_coupling, list_children, [])
                if len(circular_orders) > 1:
                    if circular_orders not in dict_circular_children_bids.values():
                        dict_circular_children_bids[index_pc_t] = circular_orders
                        index_pc_t += 1

        # Step 2 - Attributing this unique ID to each order present within a set
        for index_pc_t, orders in dict_circular_children_bids.items():
            for order in orders:
                mc_order = self.input_dataset.mc_orders[order.name]
                if mc_order.circular_pc_id is None:
                    mc_order.circular_pc_id = index_pc_t

        logger.debug(f"'Circular parent child bids sets are : {dict_circular_children_bids}")
        return dict_circular_children_bids

    # Recursively gets all the children from circular parent_child couplings
    def get_circular_children(
        self, mc_order_coupling: OrderCouplingMC, orders: list[Order], processed_order_couplings: list[str]
    ):
        parent_order, child_order = mc_order_coupling.orders[:2]
        child_mc_order = self.input_dataset.mc_orders[child_order.name]
        processed_order_couplings.append(mc_order_coupling.name)
        order_coupling_parent_ids = child_mc_order.order_coupling_parent_ids

        # A parent/child link is considered transitive when the child is also a parent elsewhere
        if child_mc_order.is_parent and order_coupling_parent_ids:
            orders.append(child_order)
            for mc_order_coupling_name in order_coupling_parent_ids:
                if mc_order_coupling_name not in processed_order_couplings:
                    self.get_circular_children(mc_order_coupling, orders, processed_order_couplings)

            return orders
        # The child is not a parent, the transitive parent/child link stops here
        else:
            return orders

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
                price_group_variable = self.get_variable(
                    constants.price_on_group_variable_name(price_group.id, price_group.time_index)
                )
                price_group_variable.SetLb(price_group.min_price)
                price_group_variable.SetUb(price_group.max_price)

    def get_idv_idr_block_sets_fast(
        self,
        order_coupling,
        block_idv_idr_bids,
        treated_order_couplings,
        index_lo,
        idr_idv_coupling_infos,
        idr_idv_order_couplings,
    ):
        for order_name in idr_idv_coupling_infos[order_coupling.name]:
            mc_order = self.input_dataset.mc_orders[order_name]
            block_idv_idr_bids.append(mc_order)
            mc_order.full_link_id = index_lo

            if order_name in idr_idv_order_couplings:
                for linked_order_coupling_name in idr_idv_order_couplings[order_name]:
                    if linked_order_coupling_name in treated_order_couplings:
                        continue
                    treated_order_couplings.append(linked_order_coupling_name)
                    linked_order_coupling = self.input_dataset.mc_order_couplings[linked_order_coupling_name]
                    block_idv_idr_bids, treated_order_couplings = self.get_idv_idr_block_sets_fast(
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
    def compute_linked_bids_sets(self):
        dict_linked_bids = {}
        index_lo = 0
        treated_order_couplings = []

        # FC: Improvement test for performance purposes
        # Begin by creating two dicts:
        # _ a dict containing, for each IDR or IDV coupling, associated order ids
        # _ a dict containing, for each order, ids of all associated IDR or IDV couplings
        complement_coupling_list = []
        idr_idv_coupling_infos = {}
        idr_idv_order_couplings = {}
        for mc_order_coupling in self.input_dataset.mc_order_couplings.values():
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
                mc_order = self.input_dataset.mc_orders[order.name]
                idr_idv_coupling_infos[mc_order_coupling.name].append(order.name)
                if order.name in idr_idv_order_couplings:
                    idr_idv_order_couplings[order.name].append(mc_order_coupling.name)
                else:
                    idr_idv_order_couplings[order.name] = [mc_order_coupling.name]

        for order_coupling_name in idr_idv_coupling_infos:
            mc_order_coupling = self.input_dataset.mc_order_couplings[order_coupling_name]
            # Check if we have already treated this order coupling
            # (Could be the case in a idv or idr block)
            if order_coupling_name in treated_order_couplings:
                continue
            treated_order_couplings.append(order_coupling_name)
            linked_bids = mc_order_coupling.orders
            circularly_linked_bids = []
            block_idv_idr_bids = []
            mc_order_coupling = self.input_dataset.mc_order_couplings[order_coupling_name]
            block_idv_idr_bids, treated_order_couplings = self.get_idv_idr_block_sets_fast(
                mc_order_coupling,
                block_idv_idr_bids,
                treated_order_couplings,
                index_lo,
                idr_idv_coupling_infos,
                idr_idv_order_couplings,
            )

            if mc_order.circular_pc_id is not None:
                circularly_linked_bids.extend(self.dict_circular_children_bids[mc_order.circular_PC_id])
                # This circular set has already been reassigned to a global linked set,
                # we can delete it from the initial dictionary
                del self.dict_circular_children_bids[mc_order.circular_pc_id]

            # Add circular parent-child orders and block identical volume (idv)
            #     and identical ratio (idr) orders
            linked_bids.extend(circularly_linked_bids)
            linked_bids.extend(block_idv_idr_bids)

            order_names = list(dict.fromkeys(order.name for order in linked_bids))
            dict_linked_bids[index_lo] = [self.input_dataset.mc_orders[order_name] for order_name in order_names]
            index_lo += 1

        for mc_order_coupling in complement_coupling_list:
            list_order_direction = []
            for order in mc_order_coupling.orders:
                mc_order = self.input_dataset.mc_orders[order.name]
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
        if len(self.dict_circular_children_bids) > 0:
            for index_pc_t in self.dict_circular_children_bids:
                dict_linked_bids[index_lo] = list(self.dict_circular_children_bids[index_pc_t])
                index_lo += 1

        # Step 3 - Instantiating full_link_id on concerned orders
        for index_lo in dict_linked_bids:
            for order in dict_linked_bids[index_lo]:
                mc_order = self.input_dataset.mc_orders[order.name]
                if mc_order.full_link_id is None:
                    mc_order.full_link_id = index_lo
        logger.debug("Dict linked bids before instantiating parent_child links : ")
        for key, values in dict_linked_bids.items():
            logger.debug(f"{key} : {values}")

        return dict_linked_bids

    # Defining global parent_child sets
    # Gets all the children from a parent set containing several parent orders
    def get_children(self, parent_orders: list[Order]) -> list[Order]:
        list_children = []
        for order in parent_orders:
            mc_order = self.input_dataset.mc_orders[order.name]
            for mc_order_coupling in self.input_dataset.mc_order_couplings.values():
                if mc_order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                    market_area_name = self.input_dataset.mc_orders[mc_order_coupling.orders[0].name].market_area.name
                    if mc_order.market_area.name == market_area_name and order.name == mc_order_coupling.orders[0].name:
                        if mc_order_coupling.orders[1] not in parent_orders:
                            list_children.append(mc_order_coupling.orders[1])
        return list_children

    # Finds global parent_child links between orders (including the links between parents to merge them as a single parent),
    # defines the resulting sets and stores them in a dictionary
    def compute_parent_child_sets(self):
        dict_parent_child_orders = {}
        index_pc = 0
        for mc_order_coupling in self.input_dataset.mc_order_couplings.values():
            if mc_order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                parent_order, child_order = mc_order_coupling.orders[:2]
                parent_mc_order = self.input_dataset.mc_orders[parent_order.name]

                # Check if the parent is linked to other bids to consider them as parent as well
                if parent_mc_order.full_link_id is not None:
                    if parent_mc_order.full_link_id in self.dict_linked_orders:
                        parent_link_orders = self.dict_linked_orders[parent_mc_order.full_link_id]
                        child_orders = self.get_children(parent_link_orders)
                        dict_parent_child_orders[index_pc] = (parent_link_orders, child_orders)
                        # The initial parent set is removed from global linked sets
                        # as it is now part of a global parent/child link
                        self.dict_linked_orders.pop(parent_mc_order.full_link_id)
                    else:
                        # One parent has already been browsed and enabled to gather all the parent orders into one set
                        continue
                else:
                    parent_orders = [parent_order]
                    dict_parent_child_orders[index_pc] = (parent_orders, [child_order])
                index_pc += 1

        for index_pc in dict_parent_child_orders:
            parent_orders = dict_parent_child_orders[index_pc][0]
            children_orders = dict_parent_child_orders[index_pc][1]
            for order in parent_orders:
                mc_order = self.input_dataset.mc_orders[order.name]
                if mc_order.full_pc_id is None:
                    mc_order.full_pc_id = index_pc
            id_child = 0
            for order in children_orders:
                mc_order = self.input_dataset.mc_orders[order.name]
                if mc_order.full_pc_id is None:
                    mc_order.full_pc_id = index_pc
                if mc_order.child_id is None:
                    mc_order.child_id = str(id_child)
                    id_child += 1

        logger.debug(f"Final linked bids dict : {self.dict_linked_orders}")
        logger.debug(f"Final parent_child bids dict : {dict_parent_child_orders}")

        return dict_parent_child_orders

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

    def retrieve_market_prices(self) -> dict[tuple[str, int], float]:
        """
        :rtype: dict[tuple[str, int], float]
        """
        market_prices = {}
        for time_index, price_groups in self.price_groups.items():
            for price_group in price_groups:
                for market_area_name in price_group.market_area_names:
                    market_price_name = constants.price_on_group_variable_name(price_group.id, time_index)
                    market_prices[market_area_name, time_index] = self.get_variable(market_price_name).solution_value()
        return market_prices
