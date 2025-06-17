"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from ortools.linear_solver import pywraplp

from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters
import atlas.modules.market_clearing.market_clearing_constants as constants


# Static definition of default bounds on exchanges (can be changed at will):
DEFAULT_MAX_FLOW = 10000.0
DEFAULT_MIN_FLOW = -10000.0


class ClearingModel:
    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.solver = None

    @staticmethod
    def create_solver_parameters(use_presolve: bool) -> pywraplp.MPSolverParameters:
        solver_params = pywraplp.MPSolverParameters()
        solver_params.PRESOLVE = int(use_presolve)
        return solver_params

    def build(self, solver_name):
        self.solver = pywraplp.Solver.CreateSolver('CBC')
        self.build_variables()
        self.build_constraints()
        self.build_objective()

    def build_variables(self):
        """ Create all variables for the clearing phase model"""
        is_atc = self.input_dataset.parameters.exchange_constraints_type == "atc"
        self.create_border_exchange_variables(is_atc)
        if self.input_dataset.parameters.flow_penalty_lambda_2 != 0.0:
            self.create_border_pos_exchanges_variables(is_atc)
            self.create_border_neg_exchange_variables(is_atc)

        if is_atc:
            self.create_border_imports_variables()
            self.create_border_exports_variables()
            self.create_border_xsis_variables()
            self.create_border_nus_variables()

        self.create_local_balances_variables()
        self.create_accepted_powers()
        self.create_orders_status()

    def build_constraints(self):
        """ Create all constraints for the clearing phase model"""
        self.create_constraint_3_4_min_constraints()
        """
        self.create_constraint_3_4_max_constraints()
        self.create_constraint_3_8_constraints()
        self.create_constraint_3_8_1_constraints()
        self.create_constraint_3_9_constraints()
        self.create_constraint_3_10_constraints()
        self.create_parent_child_constraints()
        self.create_constraint_3_2_1_constraints()
        self.create_constraint_3_2_2_constraints()
        self.create_constraint_3_5_sold_constraints()
        self.create_constraint_3_5_bought_constraints()
        if self.parameters.flow_penalty_lambda_2 != 0.0:
            self.create_constraint_3_6_1b_constraints()
            self.create_constraint_3_6_1c_constraints()
            self.create_constraint_3_6_1d_constraints()
            self.create_constraint_3_6_1f_constraints()
            self.create_constraint_3_6_1g_constraints()
        if self.parameters.exchange_constraints_type != "atc":
            self.create_constraint_3_6_2_constraints()
        self.create_absolute_exchange_constraints()
        self.create_exchange_across_border_constraints()
        """
    def build_objective(self):
        """ Create objective function for the clearing phase model"""
        objective = self.add_accepted_powers(self.parameters.price_modifier_lambda_1)
        if self.parameters.flow_penalty_lambda_2 != 0.0:
            objective -= self.add_global_exchanges()
        if self.parameters.exchange_constraints_type == "atc":
            if self.parameters.flow_penalty_lambda_3 != 0.0:
                objective -= self.add_max_exchanges()
            if self.parameters.flow_penalty_lambda_4 != 0.0:
                objective -= self.add_min_exchanges()
        self.solver.Maximize(objective)

    ##################################
    # Variables
    ##################################
    def create_border_exchange_variables(self, is_atc: bool):
        for border in self.input_dataset.market_borders:
            for time_index, time in enumerate(self.input_dataset.times):
                relative_max_flow = border.max_flow.get_value(time).sum() if is_atc else DEFAULT_MAX_FLOW
                relative_min_flow = border.min_flow.get_value(time).sum() if is_atc else DEFAULT_MIN_FLOW
                self.solver.NumVar(
                    relative_min_flow,
                    relative_max_flow,
                    constants.border_exchange_variable_name(border.name, time_index)
                )

    def create_border_pos_exchanges_variables(self, is_atc: bool):
        for border in self.input_dataset.market_borders:
            for time_index, time in enumerate(self.input_dataset.times):
                relative_max_flow = border.max_flow.get_value(time).sum() if is_atc else DEFAULT_MAX_FLOW
                self.solver.NumVar(
                    0.0,
                    relative_max_flow,
                    constants.border_pos_exchange_variable_name(border.name, time_index)
                )

    def create_border_neg_exchange_variables(self, is_atc: bool):
        for border in self.input_dataset.market_borders:
            for time_index, time in enumerate(self.input_dataset.times):
                relative_min_flow = border.min_flow.get_value(time).sum() if is_atc else DEFAULT_MIN_FLOW
                self.solver.NumVar(
                    relative_min_flow,
                    0.0,
                    constants.border_pos_exchange_variable_name(border.name, time_index)
                )

    def create_border_imports_variables(self):
        for border in self.input_dataset.market_borders:
            for time_index, time in enumerate(self.input_dataset.times):
                self.solver.NumVar(
                    -float("inf"), float("inf"), constants.border_import_variable_name(border.name, time_index)
                )

    def create_border_exports_variables(self):
        for border in self.input_dataset.market_borders:
            for time_index, time in enumerate(self.input_dataset.times):
                self.solver.NumVar(
                    -float("inf"), float("inf"), constants.border_export_variable_name(border.name, time_index)
                )

    def create_border_xsis_variables(self):
        for border in self.input_dataset.market_borders:
            for time_index, time in enumerate(self.input_dataset.times):
                self.solver.NumVar(
                    -float("inf"), float("inf"), constants.border_xsis_variable_name(border.name, time_index)
                )

    def create_border_nus_variables(self):
        for border in self.input_dataset.market_borders:
            for time_index, time in enumerate(self.input_dataset.times):
                self.solver.NumVar(
                    -float("inf"), float("inf"), constants.border_nus_variable_name(border.name, time_index)
                )

    def create_local_balances_variables(self):
        for market_area_name in self.input_dataset.mc_market_areas:
            for time_index, time in enumerate(self.input_dataset.times):
                self.solver.NumVar(
                    -float("inf"), float("inf"),
                    constants.local_balance_variable_name(market_area_name, time_index)
                )

    def create_accepted_powers(self):
        for market_area in self.input_dataset.mc_market_areas.values():
            for mc_order in market_area.orders.values():
                if mc_order.order.qmin:
                    min_power = 0.0
                    max_power = mc_order.order.qmax
                    self.solver.NumVar(
                        min_power, max_power, constants.accepted_power_variable_name(mc_order.order.name)
                    )
                else:
                    self.solver.NumVar(
                        -float("inf"), float("inf"), constants.accepted_power_variable_name(mc_order.order.name)
                    )

    def create_orders_status(self):
        for market_area in self.input_dataset.mc_market_areas.values():
            for mc_order in market_area.orders.values():
                if mc_order.id_with_status:
                    self.solver.BoolVar(constants.order_status_variable_name(mc_order.order.name))

    ##################################
    # Constraints
    ##################################
    def create_constraint_3_4_min_constraints(self):
        for market_area in self.input_dataset.mc_market_areas.values():
            for order in market_area.orders.values():
                # Compute the constraints limiting the accepted powers of combined,
                # indivisible and/or mutually excluding orders and linked orders (3.4):
                if order.id_with_status is not None:
                    order_status = self.solver.LookupVariable(constants.order_status_variable_name(order.order.name))
                    accepted_power = self.solver.LookupVariable(constants.accepted_power_variable_name(order.order.name))
                    self.solver.Add(
                        order_status * max(self.parameters.allowed_round_off_error, order.order.qmin)
                        <= accepted_power,
                        constants.constraint_3_4_min_constraint_name(market_area.market_area.name, order.order.name)
                    )
    ##################################
    # Objective
    ##################################
    def add_accepted_powers(self, lambda1: float):
        objective = 0.0
        for market_area in self.input_dataset.mc_market_areas.values():
            for order in market_area.orders.values():
                accepted_power = self.solver.LookupVariable(constants.accepted_power_variable_name(order.order.name))
                altered_price = order.order.price - order.production_sign * lambda1
                objective -= order.production_sign * altered_price * order.duration * accepted_power / 60
        return objective

    def add_global_exchanges(self):
        pass

    def add_max_exchanges(self):
        pass

    def add_min_exchanges(self):
        pass