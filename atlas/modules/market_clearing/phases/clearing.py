"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from ortools.linear_solver import pywraplp  # type: ignore[attr-defined]

import atlas.modules.market_clearing.market_clearing_constants as constants
from atlas.config import logger
from atlas.enum import ComplementDirection, CouplingType, OrderType
from atlas.models.control_block import ControlBlock
from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import ExchangeConstraintsType, MarketClearingParameters
from atlas.modules.market_clearing.models.control_block_mc import ControlBlockMC
from atlas.modules.market_clearing.models.market_area_mc import MarketAreaMC
from atlas.modules.market_clearing.models.order_coupling_mc import OrderCouplingMC
from atlas.modules.market_clearing.models.order_mc import OrderMC
from atlas.solver.solver_interface import OptimisationModel

# Static definition of default bounds on exchanges (can be changed at will):
DEFAULT_MAX_FLOW = 10000.0
DEFAULT_MIN_FLOW = -10000.0


class Clearing(OptimisationModel):
    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        super().__init__(parameters.solver_name)
        self.input_dataset = input_dataset
        self.parameters = parameters

    @staticmethod
    def create_solver_parameters(use_presolve: bool) -> pywraplp.MPSolverParameters:
        solver_params = pywraplp.MPSolverParameters()
        solver_params.PRESOLVE = int(use_presolve)
        return solver_params

    def run(self):
        self.build()
        self.solve()
        if self.parameters.export_lp:
            self.export_model("clearing_model.lp")

    def build(self):
        self.build_variables()
        self.build_constraints()
        self.build_objective()

    def build_variables(self):
        """Create all variables for the clearing phase model"""
        is_atc = self.input_dataset.parameters.exchange_constraints_type == ExchangeConstraintsType.ATC
        self.create_border_exchange_variables(is_atc)
        if self.input_dataset.parameters.flow_penalty_lambda_2 != 0.0:
            self.create_border_pos_exchanges_variables(is_atc)
            self.create_border_neg_exchanges_variables(is_atc)

        if is_atc:
            self.create_border_imports_variables()
            self.create_border_exports_variables()
            self.create_border_xsis_variables()
            self.create_border_nus_variables()

        self.create_local_balances_variables()
        self.create_accepted_powers()
        self.create_orders_status()

    def build_constraints(self):
        """Create all constraints for the clearing phase model"""
        is_atc = self.input_dataset.parameters.exchange_constraints_type == ExchangeConstraintsType.ATC
        self.create_limited_accepted_power_constraints()
        self.create_order_couplings_constraints()
        self.create_local_balances_constraints()
        self.create_exchanges_and_local_balances_equality_constraints(is_atc)
        if self.parameters.activate_constrained_tso_quantity:
            self.create_control_blocks_constraints()
        self.create_exchange_across_border_constraints()
        if is_atc and self.get_n_borders_with_losses():
            self.create_import_export_constraints()

        if not is_atc:
            self.create_constraint_3_6_2_constraints()
        if self.parameters.flow_penalty_lambda_2 != 0.0:
            self.create_absolute_exchange_constraints()

    def build_objective(self):
        """Create objective function for the clearing phase model"""
        self.add_accepted_powers(self.parameters.price_modifier_lambda_1)
        if self.parameters.flow_penalty_lambda_2 != 0.0:
            self.add_global_exchanges(self.parameters.flow_penalty_lambda_2)
        if self.parameters.exchange_constraints_type == ExchangeConstraintsType.ATC:
            exchange_objective_dict = {}
            if self.parameters.flow_penalty_lambda_3 != 0.0:
                for key, value in self.add_max_exchanges(self.parameters.flow_penalty_lambda_3).items():
                    exchange_objective_dict[key.name()] = value
            if self.parameters.flow_penalty_lambda_4 != 0.0:
                for key, value in self.add_min_exchanges(self.parameters.flow_penalty_lambda_4).items():
                    if key.name() not in exchange_objective_dict:
                        exchange_objective_dict[key.name()] = value
                    else:
                        exchange_objective_dict[key.name()] += value
            self.add_objective(sum([self.get_variable(key) * value for key, value in exchange_objective_dict.items()]),
                               direction="maximize")


    ##################################
    # Variables
    ##################################
    def create_border_exchange_variables(self, is_atc: bool):
        for border_name, mc_border in self.input_dataset.mc_market_borders.items():
            for time_index, _time in enumerate(self.input_dataset.times):
                relative_max_flow = mc_border.max_flow.get_value(_time) if is_atc else float("inf")
                relative_min_flow = mc_border.min_flow.get_value(_time) if is_atc else float("-inf")
                self.add_continuous_variable(
                    constants.border_exchange_variable_name(border_name, time_index),
                    relative_min_flow,
                    relative_max_flow,
                )

    def create_border_pos_exchanges_variables(self, is_atc: bool):
        for border_name, mc_border in self.input_dataset.mc_market_borders.items():
            for time_index, _time in enumerate(self.input_dataset.times):
                relative_max_flow = mc_border.max_flow.get_value(_time) if is_atc else DEFAULT_MAX_FLOW
                self.add_continuous_variable(
                    constants.border_pos_exchange_variable_name(border_name, time_index), 0.0, relative_max_flow
                )

    def create_border_neg_exchanges_variables(self, is_atc: bool):
        for border_name, mc_border in self.input_dataset.mc_market_borders.items():
            for time_index, _time in enumerate(self.input_dataset.times):
                relative_min_flow = mc_border.min_flow.get_value(_time) if is_atc else DEFAULT_MIN_FLOW
                self.add_continuous_variable(
                    constants.border_neg_exchange_variable_name(border_name, time_index), relative_min_flow, 0.0
                )

    def create_border_imports_variables(self):
        for border_name, mc_border in self.input_dataset.mc_market_borders.items():
            for time_index, _ in enumerate(self.input_dataset.times):
                if mc_border.loss_factor and mc_border.loss_factor != 0.0:
                    self.add_continuous_variable(
                        constants.border_import_variable_name(border_name, time_index), -float("inf"), float("inf")
                    )

    def create_border_exports_variables(self):
        for border_name, mc_border in self.input_dataset.mc_market_borders.items():
            for time_index, _ in enumerate(self.input_dataset.times):
                if mc_border.loss_factor and mc_border.loss_factor != 0.0:
                    self.add_continuous_variable(
                        constants.border_export_variable_name(border_name, time_index), -float("inf"), float("inf")
                    )

    def create_border_xsis_variables(self):
        for border_name, mc_border in self.input_dataset.mc_market_borders.items():
            for time_index, _ in enumerate(self.input_dataset.times):
                if mc_border.loss_factor and mc_border.loss_factor != 0.0:
                    self.add_continuous_variable(
                        constants.border_xsis_variable_name(border_name, time_index), -float("inf"), float("inf")
                    )

    def create_border_nus_variables(self):
        for border_name, mc_border in self.input_dataset.mc_market_borders.items():
            for time_index, _ in enumerate(self.input_dataset.times):
                if mc_border.loss_factor and mc_border.loss_factor != 0.0:
                    self.add_continuous_variable(
                        constants.border_nus_variable_name(border_name, time_index), -float("inf"), float("inf")
                    )

    def create_local_balances_variables(self):
        for market_area_name in self.input_dataset.mc_market_areas:
            for time_index, _ in enumerate(self.input_dataset.times):
                self.add_continuous_variable(
                    constants.local_balance_variable_name(market_area_name, time_index), -float("inf"), float("inf")
                )

    def create_accepted_powers(self):
        for mc_market_area in self.input_dataset.mc_market_areas.values():
            for mc_order in mc_market_area.mc_orders.values():
                if not mc_order.qmin:
                    max_power = mc_order.qmax
                    self.add_continuous_variable(constants.accepted_power_variable_name(mc_order.market_area.name, mc_order.name), 0.0, max_power)
                else:
                    self.add_continuous_variable(
                        constants.accepted_power_variable_name(mc_order.market_area.name, mc_order.name), -float("inf"), float("inf")
                    )

    def create_orders_status(self):
        for mc_market_area in self.input_dataset.mc_market_areas.values():
            for mc_order in mc_market_area.mc_orders.values():
                mc_order = self.input_dataset.mc_orders[mc_order.name]
                if mc_order.id_with_status:
                    self.add_boolean_variable(constants.order_status_variable_name(mc_market_area.name, mc_order.name))

    ##################################
    # Constraints
    ##################################
    def create_local_balances_constraints(self):
        for time_index, time in enumerate(self.input_dataset.times):
            for mc_market_area in self.input_dataset.mc_market_areas.values():
                accepted_powers = []
                for mc_order in mc_market_area.mc_orders.values():
                    # Focus on orders comprising the current time in their duration:
                    if mc_order.start_date <= time < mc_order.end_date_processed:
                        accepted_power = self.get_variable(constants.accepted_power_variable_name(mc_order.market_area.name, mc_order.name))
                        accepted_powers.append(mc_order.production_sign * accepted_power)
                local_balance = self.get_variable(
                    constants.local_balance_variable_name(mc_market_area.name, time_index)
                )
                self.add_constraint(
                    sum(accepted_powers) == local_balance,
                    constants.constraint_3_2_1_constraint_name(mc_market_area.name, time_index),
                )

    def create_exchanges_and_local_balances_equality_constraints(self, is_atc):
        for time_index, _ in enumerate(self.input_dataset.times):
            for market_area_name, mc_market_area in self.input_dataset.mc_market_areas.items():
                exchanges_sum = []
                for border_name, mc_border in self.input_dataset.mc_market_borders.items():
                    if market_area_name not in [
                        mc_border.uphill_market_area.name,
                        mc_border.downhill_market_area.name,
                    ]:
                        continue
                    if is_atc and mc_border.loss_factor and mc_border.loss_factor != 0.0:
                        if mc_border.uphill_market_area.name == market_area_name:
                            exchanges_sum.append(
                                self.get_variable(constants.border_export_variable_name(border_name, time_index))
                            )
                        elif mc_border.downhill_market_area.name == market_area_name:
                            exchanges_sum.append(
                                -self.get_variable(constants.border_import_variable_name(border_name, time_index))
                            )
                    else:
                        border_sign = 1 if market_area_name == mc_border.uphill_market_area.name else -1
                        exchanges_sum.append(
                            border_sign
                            * self.get_variable(constants.border_exchange_variable_name(border_name, time_index))
                        )
                self.add_constraint(
                    self.get_variable(constants.local_balance_variable_name(market_area_name, time_index))
                    == sum(exchanges_sum),
                    constants.constraint_3_2_2_constraint_name(market_area_name, time_index),
                )

    def create_control_blocks_constraints(self):
        for time_index, time in enumerate(self.input_dataset.times):
            for control_block_name, control_block in self.input_dataset.mc_control_blocks.items():
                tso_sold_power = self.get_tso_sold_power(time, control_block)
                tso_bought_power = self.get_tso_bought_power(time, control_block)
                max_tso_sold_power = Clearing.get_max_tso_power_sold(
                    time, control_block, self.input_dataset.mc_market_areas
                )
                max_tso_bought_power = Clearing.get_max_tso_power_bought(
                    time, control_block, self.input_dataset.mc_market_areas
                )
                self.add_constraint(
                    tso_sold_power <= max_tso_sold_power,
                    constants.constraint_3_5_sold_constraint_name(control_block_name, time_index),
                )
                self.add_constraint(
                    tso_bought_power <= max_tso_bought_power,
                    constants.constraint_3_5_bought_constraint_name(control_block_name, time_index),
                )

    def create_exchange_across_border_constraints(self):
        for time_index, time in enumerate(self.input_dataset.times):
            for border_name, mc_border in self.input_dataset.mc_market_borders.items():
                if mc_border.time_resolution > self.parameters.time_step.total_minutes():
                    time_elapsed = time - self.parameters.start_date
                    # % and / have same precedence => parsed left to right
                    res_offset = (
                        time_elapsed.minutes % mc_border.time_resolution / self.parameters.time_step.total_minutes()
                    )
                    if res_offset != 0:
                        precedent_time_index = res_offset * self.parameters.time_step.total_minutes()
                        self.add_constraint(
                            self.get_variable(constants.border_exchange_variable_name(border_name, time_index))
                            == self.get_variable(
                                constants.border_exchange_variable_name(border_name, precedent_time_index)
                            ),
                            constants.exchange_across_border_constraint_name(border_name, time_index),
                        )

    def create_import_export_constraints(self):
        for time_index, _ in enumerate(self.input_dataset.times):
            for border_name, mc_border in self.input_dataset.mc_market_borders.items():
                if mc_border.loss_factor is None or mc_border.loss_factor == 0:
                    continue
                exchange = self.get_variable(constants.border_exchange_variable_name(border_name, time_index))
                _import = self.get_variable(constants.border_import_variable_name(border_name, time_index))
                _export = self.get_variable(constants.border_export_variable_name(border_name, time_index))
                xsis = self.get_variable(constants.border_xsis_variable_name(border_name, time_index))
                nus = self.get_variable(constants.border_nus_variable_name(border_name, time_index))

                self.add_constraint(
                    exchange == 0.5 * (_import + _export),
                    constants.constraint_3_6_1b_constraint_name(border_name, time_index),
                )

                tmp_rhs = ((1.0 - mc_border.loss_factor) - 1.0 / (1.0 - mc_border.loss_factor)) * xsis + _export / (
                    1.0 - mc_border.loss_factor
                )
                self.add_constraint(
                    _import == tmp_rhs, constants.constraint_3_6_1c_constraint_name(border_name, time_index)
                )
                self.add_constraint(
                    xsis >= 0.5 * _export, constants.constraint_3_6_1d_constraint_name(border_name, time_index)
                )

                if exchange.Lb():
                    self.add_constraint(
                        nus * exchange.Lb() <= xsis,
                        constants.constraint_3_6_1f_min_constraint_name(border_name, time_index),
                    )
                    self.add_constraint(
                        (1 - nus) * exchange.Lb() >= _export - xsis,
                        constants.constraint_3_6_1g_min_constraint_name(border_name, time_index),
                    )

                if exchange.Ub():
                    self.add_constraint(
                        nus * exchange.Ub() <= xsis,
                        constants.constraint_3_6_1f_min_constraint_name(border_name, time_index),
                    )
                    self.add_constraint(
                        (1 - nus) * exchange.Ub() >= _export - xsis,
                        constants.constraint_3_6_1g_min_constraint_name(border_name, time_index),
                    )

    def create_absolute_exchange_constraints(self):
        for time_index, _ in enumerate(self.input_dataset.times):
            for border_name in self.input_dataset.mc_market_borders.keys():
                border_exchange = self.get_variable(constants.border_exchange_variable_name(border_name, time_index))
                border_pos_exchange = self.get_variable(
                    constants.border_pos_exchange_variable_name(border_name, time_index)
                )
                border_neg_exchange = self.get_variable(
                    constants.border_neg_exchange_variable_name(border_name, time_index)
                )
                absolute_exchange_constraint_name = constants.absolute_exchange_constraint_name(border_name, time_index)
                self.add_constraint(
                    border_pos_exchange + border_neg_exchange == border_exchange, absolute_exchange_constraint_name
                )

    def create_constraint_3_6_2_constraints(self):
        for time_index, time in enumerate(self.input_dataset.times):
            for critical_branch_name, mc_critical_branch in self.input_dataset.mc_critical_branches.items():
                branch_load = []
                for market_area_ptdf in mc_critical_branch.market_area_ptdf:
                    mc_market_area_ptdf = self.input_dataset.mc_market_area_ptdfs[market_area_ptdf.name]
                    da_ptdf = mc_market_area_ptdf.day_ahead_ptdf
                    mc_market_area = self.input_dataset.mc_market_areas[mc_market_area_ptdf.market_area.name]
                    relative_balance = (self.get_variable(constants.local_balance_variable_name(
                        mc_market_area.name, time_index))
                                        - mc_market_area.ref_balance.get_value(time))

                    branch_load.append(da_ptdf.get_value(time) * relative_balance)
                self.add_constraint(
                    sum(branch_load) <= mc_critical_branch.max_flow.get_value(time),
                    constants.constraint_3_6_2_constraint_name(critical_branch_name, time_index),
                )

    def create_limited_accepted_power_constraints(self):
        for mc_market_area in self.input_dataset.mc_market_areas.values():
            for mc_order in mc_market_area.mc_orders.values():
                # Compute the constraints limiting the accepted powers of combined,
                # indivisible and/or mutually excluding orders and linked orders (3.4):
                if mc_order.id_with_status:
                    order_status = self.get_variable(constants.order_status_variable_name(mc_market_area.name, mc_order.name))
                    accepted_power = self.get_variable(constants.accepted_power_variable_name(mc_order.market_area.name, mc_order.name))
                    self.create_min_accepted_power_constraint(
                        mc_market_area.name,
                        mc_order.name,
                        order_status,
                        mc_order.qmin,
                        accepted_power,
                    )
                    self.create_max_accepted_power_constraint(
                        mc_market_area.name,
                        mc_order.name,
                        order_status,
                        mc_order.qmax,
                        accepted_power,
                    )

    def create_min_accepted_power_constraint(
        self, market_area_name: str, order_name: str, order_status, min_power: float, accepted_power
    ):
        self.add_constraint(
            order_status * max(self.parameters.allowed_round_off_error, min_power) <= accepted_power,
            constants.min_accepted_power_constraint_name(market_area_name, order_name),
        )

    def create_max_accepted_power_constraint(
        self, market_area_name: str, order_name: str, order_status, max_power: float, accepted_power
    ):
        self.add_constraint(
            order_status * max_power >= accepted_power,
            constants.max_accepted_power_constraint_name(market_area_name, order_name),
        )

    def create_order_couplings_constraints(self):
        for order_coupling in self.input_dataset.mc_order_couplings.values():
            match order_coupling.coupling_type:
                case CouplingType.IDENTICAL_VOLUME:
                    self.create_identical_volume_order_coupling_constraints(order_coupling)
                case CouplingType.IDENTICAL_RATIO:
                    self.create_identical_ratio_order_coupling_constraints(order_coupling)
                case CouplingType.COMPLEMENT:
                    self.create_complement_order_coupling_constraints(order_coupling)
                case CouplingType.EXCLUSION:
                    self.create_exclusion_order_coupling_constraints(order_coupling)
                case CouplingType.PARENT_CHILDREN:
                    self.create_parent_children_order_coupling_constraints(order_coupling)

    def create_identical_volume_order_coupling_constraints(self, order_coupling: OrderCouplingMC):
        for i, order in enumerate(order_coupling.orders[1:]):
            prev_order = order_coupling.orders[i]
            prev_accepted_power = self.get_variable(constants.accepted_power_variable_name(prev_order.market_area.name, prev_order.name))
            accepted_power = self.get_variable(constants.accepted_power_variable_name(order.market_area.name, order.name))

            self.add_constraint(
                accepted_power == prev_accepted_power,
                constants.identical_volume_order_coupling_constraint_name(order_coupling.name, order.name),
            )

    def create_complement_order_coupling_constraints(self, order_coupling: OrderCouplingMC):
        if not order_coupling.complement_direction:
            logger.info(
                f"Can't create constraint complement order coupling ('{order_coupling.name}') because there is not "
                f"complement_direction"
            )
            return
        aggregated_accepted_power = []
        for order in order_coupling.orders:
            if not OrderMC.is_feasible(order, self.input_dataset.times, self.parameters):
                continue
            accepted_power = self.get_variable(constants.accepted_power_variable_name(order.market_area.name, order.name))
            mc_order = self.input_dataset.mc_orders[order.name]
            if mc_order.order_type == OrderType.Sell:
                aggregated_accepted_power.append(-accepted_power)
            elif mc_order.order_type == OrderType.Buy:
                aggregated_accepted_power.append(accepted_power)
            else:
                logger.info(
                    f"Can't create constraint complement order coupling ('{order_coupling.name}') on "
                    f"'{order.name}' because the order type '{mc_order.order_type.value}' is not implemented"
                )
        aggregated_proportion_accepted_power = (
            sum(aggregated_accepted_power) * self.parameters.time_step.total_minutes() / 60
        )
        constraint_name = constants.constraint_3_9_constraint_name(order_coupling.name)
        if order_coupling.complement_direction == ComplementDirection.EqualTo:
            self.add_constraint(
                aggregated_proportion_accepted_power == order_coupling.complement_energy, constraint_name
            )
        elif order_coupling.complement_direction == ComplementDirection.GreaterThan:
            self.add_constraint(
                aggregated_proportion_accepted_power >= order_coupling.complement_energy, constraint_name
            )
        elif order_coupling.complement_direction == ComplementDirection.LesserThan:
            self.add_constraint(
                aggregated_proportion_accepted_power <= order_coupling.complement_energy, constraint_name
            )
        else:
            logger.info(
                f"Can't create constraint complement order coupling ('{order_coupling.name}') because complement"
                f" direction '{order_coupling.complement_direction.value}' is not implemented"
            )

    def create_exclusion_order_coupling_constraints(self, order_coupling: OrderCouplingMC):
        aggregated_status = []
        for order in order_coupling.orders:
            if not OrderMC.is_feasible(order, self.input_dataset.times, self.parameters):
                continue
            order_status = self.get_variable(constants.order_status_variable_name(order.market_area.name, order.name))
            aggregated_status.append(order_status)
        self.add_constraint(
            sum(aggregated_status) <= 1, constants.exclusion_order_coupling_constraint_name(order_coupling.name)
        )

    def create_parent_children_order_coupling_constraints(self, order_coupling: OrderCouplingMC):
        parent_order = order_coupling.orders[0]
        if not OrderMC.is_feasible(parent_order, self.input_dataset.times, self.parameters):
            return
        parent_order_status = self.get_variable(constants.order_status_variable_name(parent_order.market_area.name, parent_order.name))
        for order in order_coupling.orders[1:]:
            if not OrderMC.is_feasible(order, self.input_dataset.times, self.parameters):
                continue
            order_status = self.get_variable(constants.order_status_variable_name(order.market_area.name, order.name))
            self.add_constraint(
                order_status <= parent_order_status,
                constants.parent_child_order_coupling_constraint_name(order_coupling.name, order.market_area.name),
            )

    def create_identical_ratio_order_coupling_constraints(self, order_coupling: OrderCouplingMC):
        for i, order in enumerate(order_coupling.orders[1:]):
            prev_order = order_coupling.orders[i]
            prev_accepted_power = self.get_variable(constants.accepted_power_variable_name(prev_order.market_area.name, prev_order.name))
            accepted_power = self.get_variable(constants.accepted_power_variable_name(order.market_area.name, order.name))
            if prev_order.qmin == prev_order.qmax:
                prev_ratio = prev_accepted_power / prev_order.qmax
            else:
                prev_ratio = (prev_accepted_power - prev_order.qmin) / (prev_order.qmax - prev_order.qmin)
            if order.qmin == order.qmax:
                ratio = accepted_power / order.qmax
            else:
                ratio = (accepted_power - order.qmin) / (order.qmax - order.qmin)

            self.add_constraint(
                ratio == prev_ratio,
                constants.identical_ratio_order_coupling_constraint_name(order_coupling.name, order.name),
            )

    ##################################
    # Objective
    ##################################
    def add_accepted_powers(self, lambda1: float):
        objective = []
        for mc_market_area in self.input_dataset.mc_market_areas.values():
            for mc_order in mc_market_area.mc_orders.values():
                accepted_power = self.get_variable(constants.accepted_power_variable_name(mc_order.market_area.name, mc_order.name))
                altered_price = mc_order.price - mc_order.production_sign * lambda1
                objective.append(-mc_order.production_sign * altered_price * mc_order.duration * accepted_power / 60)
        return self.add_objective(sum(objective), direction="maximize")

    def add_global_exchanges(self, lambda2: float):
        objective = []
        for time_index, _ in enumerate(self.input_dataset.times):
            for border_name in self.input_dataset.mc_market_borders.keys():
                border_pos_exchanges = self.get_variable(
                    constants.border_pos_exchange_variable_name(border_name, time_index)
                )
                border_neg_exchanges = self.get_variable(
                    constants.border_neg_exchange_variable_name(border_name, time_index)
                )
                objective.append(border_pos_exchanges - border_neg_exchanges)
        return self.add_objective(-lambda2 * sum(objective), direction="maximize")

    def add_max_exchanges(self, lambda4: float) -> dict:
        objective = {}
        constant = 0.0
        for time_index, _ in enumerate(self.input_dataset.times):
            for border_name in self.input_dataset.mc_market_borders.keys():
                border_exchange = self.get_variable(constants.border_exchange_variable_name(border_name, time_index))
                objective[border_exchange] = lambda4
                constant -= lambda4 * border_exchange.Lb()
        return objective

    def add_min_exchanges(self, lambda4: float) -> dict:
        objective = {}
        constant = 0.0
        for time_index, _ in enumerate(self.input_dataset.times):
            for border_name in self.input_dataset.mc_market_borders.keys():
                border_exchange = self.get_variable(constants.border_exchange_variable_name(border_name, time_index))
                objective[border_exchange] = -lambda4
                constant += lambda4 * border_exchange.Lb()
        return objective

    def get_tso_sold_power(self, time: int, control_block: ControlBlockMC):
        tso_sold_power = 0.0
        for mc_market_area in self.input_dataset.mc_market_areas.values():
            if control_block.name == mc_market_area.control_block.name:
                for order_name, mc_order in mc_market_area.mc_orders.items():
                    is_available = mc_order.start_date <= time <= mc_order.end_date_processed
                    not_tso = not mc_order.is_agent_tso
                    not_sale = mc_order.order_type == OrderType.Buy
                    if is_available and not_tso and not_sale:
                        tso_sold_power += self.get_variable(constants.accepted_power_variable_name(mc_order.market_area.name, order_name))
        return tso_sold_power

    def get_tso_bought_power(self, time: int, control_block: ControlBlockMC):
        tso_bought_power = []
        for mc_market_area in self.input_dataset.mc_market_areas.values():
            if control_block.name == mc_market_area.control_block.name:
                for order_name, mc_order in mc_market_area.mc_orders.items():
                    is_available = mc_order.start_date <= time <= mc_order.end_date_processed
                    not_tso = not mc_order.is_agent_tso
                    is_sale = mc_order.order_type == OrderType.Sell
                    if is_available and not_tso and is_sale:
                        tso_bought_power.append(self.get_variable(constants.accepted_power_variable_name(mc_order.market_area.name, order_name)))
        return sum(tso_bought_power)

    @staticmethod
    def get_max_tso_power_sold(time, control_block: ControlBlock, mc_market_areas: dict[str, MarketAreaMC]) -> float:
        max_tso_power_sold = []
        for mc_market_area in mc_market_areas.values():
            if control_block == mc_market_area.control_block:
                for mc_order in mc_market_area.mc_orders.values():
                    is_available = mc_order.start_date <= time <= mc_order.end_date_processed
                    not_tso = not mc_order.is_agent_tso
                    not_sale = mc_order.order_type == OrderType.Buy
                    if is_available and not_tso and not_sale:
                        max_tso_power_sold.append(mc_order.qmax)
        return sum(max_tso_power_sold)

    @staticmethod
    def get_max_tso_power_bought(time, control_block: ControlBlock, mc_market_areas: dict[str, MarketAreaMC]) -> float:
        max_tso_power_bought = []
        for mc_market_area in mc_market_areas.values():
            if control_block == mc_market_area.control_block:
                for mc_order in mc_market_area.mc_orders.values():
                    is_available = mc_order.start_date <= time <= mc_order.end_date_processed
                    not_tso = not mc_order.is_agent_tso
                    is_sale = mc_order.order_type == OrderType.Sell
                    if is_available and not_tso and is_sale:
                        max_tso_power_bought.append(mc_order.qmax)
        return sum(max_tso_power_bought)

    def get_n_borders_with_losses(self) -> int:
        """ get the number of border that have a loss factor

        :rtype: int
        """
        n_borders_with_losses = 0
        for mc_market_border in self.input_dataset.mc_market_borders.values():
            if mc_market_border.loss_factor and mc_market_border.loss_factor != 0.0:
                n_borders_with_losses += 1
        return n_borders_with_losses

    def retrieve_local_balances(self) -> dict[tuple[str, int], float]:
        """ Retrieve the power balance for each market area at each timestep

        :rtype: dict[tuple[str, str], float]
        """
        local_balances = {}
        for market_area_name in self.input_dataset.mc_market_areas:
            for time_index, _ in enumerate(self.input_dataset.times):
                accepted_power_name = constants.local_balance_variable_name(market_area_name, time_index)
                local_balances[market_area_name, time_index] = self.get_variable(accepted_power_name).solution_value()
        return local_balances

    def retrieve_accepted_powers(self) -> dict[tuple[str, str], float]:
        """ Retrieve tje accepted powers of each order per area

        :rtype: dict[tuple[str, str], float]
        """
        accepted_powers = {}
        for mc_market_area in self.input_dataset.mc_market_areas.values():
            for mc_order in mc_market_area.mc_orders.values():
                accepted_power_name = constants.accepted_power_variable_name(mc_order.market_area.name, mc_order.name)
                accepted_powers[mc_order.market_area.name, mc_order.name] = self.get_variable(accepted_power_name).solution_value()
        return accepted_powers

    def retrieve_saturated_critical_branch(self) -> dict[tuple[str, int], float]:
        """ Retrieve the slack value of each critical branch at each timestep

        :rtype: dict[tuple[str, int], float]
        """
        saturated_critical_branch = {}
        for time_index, _ in enumerate(self.input_dataset.times):
            for critical_branch_name in self.input_dataset.mc_critical_branches:
                critical_branch_saturation = self.get_constraint_slack_value(constants.constraint_3_6_2_constraint_name(
                    critical_branch_name, time_index)
                )
                saturated_critical_branch[critical_branch_name, time_index] = critical_branch_saturation
        return saturated_critical_branch
