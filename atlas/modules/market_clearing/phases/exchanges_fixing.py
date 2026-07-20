"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import json

import atlas.modules.market_clearing.constants as constants
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.parameters import ExchangeConstraintsType, MarketClearingParameters
from atlas.modules.market_clearing.phases import _border_variables
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel


class ExchangesFixing(OptimisationModel):
    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        solver_options = SolverOptions(presolve=parameters.solver.use_presolve)

        super().__init__(parameters.solver.solver_name, options=solver_options, name="ExchangesFixing")
        self.input_dataset = input_dataset
        self.parameters = parameters

    def compute(self, clearing_local_balances: dict[tuple[str, int], float]):
        self.build(clearing_local_balances)
        self.solve()
        if self.parameters.solver.export_lp:
            output_path = self.parameters.get_lp_dir()
            output_path.mkdir(parents=True, exist_ok=True)
            self.export_model(str(output_path / "exchanges_fixing_model.lp"))

            with open(output_path / "exchanges_fixing_border_exchanges.json", "w") as f:
                json.dump([[b, time_index, val] for (b, time_index), val in self.get_border_exchanges().items()], f)

    def build(self, clearing_local_balances: dict[tuple[str, int], float]):
        self.build_variables()
        self.build_constraints(clearing_local_balances)
        self.build_objective()

    def build_variables(self):
        """Create all variables for the exchange fixing phase model"""
        is_atc = self.input_dataset.parameters.exchange_constraints_type == ExchangeConstraintsType.ATC
        self.create_border_exchange_variables(is_atc)
        self.create_border_pos_exchanges_variables(is_atc)
        self.create_border_neg_exchanges_variables(is_atc)

        if is_atc:
            self.create_border_imports_variables()
            self.create_border_exports_variables()
            self.create_border_xsis_variables()
            self.create_border_nus_variables()

    def build_constraints(self, clearing_local_balances: dict[tuple[str, int], float]):
        """Create all constraints for the exchange fixing phase model"""
        is_atc = self.input_dataset.parameters.exchange_constraints_type == ExchangeConstraintsType.ATC
        self.create_exchanges_constraints(is_atc, clearing_local_balances)
        self.create_absolute_timed_exchanges_constraints(is_atc)
        if is_atc and self.get_n_borders_with_losses():
            self.create_borders_constraints()

    def build_objective(self):
        """Create objective function for the exchanges fixing phase model"""
        objective = []
        for border_name in self.input_dataset.mc_market_borders.keys():
            for time_index, _time in enumerate(self.input_dataset.times):
                border_pos_exchange = self.get_variable(
                    constants.border_pos_exchange_variable_name(border_name, time_index)
                )
                border_neg_exchange = self.get_variable(
                    constants.border_neg_exchange_variable_name(border_name, time_index)
                )
                objective.append(border_pos_exchange - border_neg_exchange)
        self.solver.Maximize(sum(objective))

    ##################################
    # Variables
    ##################################
    def create_border_exchange_variables(self, is_atc: bool):
        _border_variables.create_border_exchange_variables(self, is_atc)

    def create_border_imports_variables(self):
        _border_variables.create_border_loss_variables(
            self, constants.border_import_variable_name, only_borders_with_losses=False
        )

    def create_border_exports_variables(self):
        _border_variables.create_border_loss_variables(
            self, constants.border_export_variable_name, only_borders_with_losses=False
        )

    def create_border_xsis_variables(self):
        _border_variables.create_border_loss_variables(
            self, constants.border_xsis_variable_name, only_borders_with_losses=False
        )

    def create_border_nus_variables(self):
        _border_variables.create_border_loss_variables(
            self, constants.border_nus_variable_name, only_borders_with_losses=False
        )

    def create_border_pos_exchanges_variables(self, is_atc: bool):
        _border_variables.create_border_pos_exchanges_variables(self, is_atc)

    def create_border_neg_exchanges_variables(self, is_atc: bool):
        _border_variables.create_border_neg_exchanges_variables(self, is_atc)

    ##################################
    # Constraints
    ##################################
    def create_exchanges_constraints(self, is_atc: bool, clearing_local_balances: dict[tuple[str, int], float]):
        for time_index, _time in enumerate(self.input_dataset.times):
            for market_area_name in self.input_dataset.mc_market_areas:
                if is_atc:
                    exchange_sum = self.compute_atc_exchange_sum_for_market_area(market_area_name, time_index)
                else:
                    exchange_sum = self.compute_fb_exchange_sum_for_market_area(market_area_name, time_index)
                constraint_name = constants.constraint_4_2_constraint_name(market_area_name, time_index)
                clearing_exchange_value = clearing_local_balances[market_area_name, time_index]
                self.add_constraint(clearing_exchange_value == exchange_sum, constraint_name)

    def compute_atc_exchange_sum_for_market_area(self, market_area_name: str, time_index: int):
        """Compute the sum of exchange in a market area when atc"""
        exchanges_sum = []
        for border_name, mc_border in self.input_dataset.mc_market_borders.items():
            if market_area_name not in [
                mc_border.uphill_market_area.name,
                mc_border.downhill_market_area.name,
            ]:
                continue
            if mc_border.loss_factor != 0.0:
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
                    border_sign * self.get_variable(constants.border_exchange_variable_name(border_name, time_index))
                )
        return sum(exchanges_sum)

    def compute_fb_exchange_sum_for_market_area(self, market_area_name: str, time_index: int):
        """Compute the sum of exchange in a market area when fb"""
        exchanges_sum = []
        for border_name, mc_border in self.input_dataset.mc_market_borders.items():
            if market_area_name not in [
                mc_border.uphill_market_area.name,
                mc_border.downhill_market_area.name,
            ]:
                continue
            border_sign = 1 if market_area_name == mc_border.uphill_market_area.name else -1
            exchanges_sum.append(
                border_sign * self.get_variable(constants.border_exchange_variable_name(border_name, time_index))
            )
        return sum(exchanges_sum)

    def create_absolute_timed_exchanges_constraints(self, is_atc: bool):
        for time_index, _ in enumerate(self.input_dataset.times):
            for border_name, mc_border in self.input_dataset.mc_market_borders.items():
                timed_pos_exchanges = self.get_variable(
                    constants.border_pos_exchange_variable_name(border_name, time_index)
                )
                timed_neg_exchanges = self.get_variable(
                    constants.border_neg_exchange_variable_name(border_name, time_index)
                )
                # Compute the sum of the absolute values of exchanges:
                if is_atc and mc_border.loss_factor != 0.0:
                    timed_exports = self.get_variable(constants.border_export_variable_name(border_name, time_index))
                    timed_imports = self.get_variable(constants.border_import_variable_name(border_name, time_index))
                    self.add_constraint(
                        timed_pos_exchanges + timed_neg_exchanges == 0.5 * (timed_imports + timed_exports),
                        constants.absolute_timed_exchanges_constraint_name(border_name, time_index),
                    )
                else:
                    timed_exchanges = self.get_variable(
                        constants.border_exchange_variable_name(border_name, time_index)
                    )
                    self.add_constraint(
                        timed_pos_exchanges + timed_neg_exchanges == timed_exchanges,
                        constants.absolute_timed_exchanges_constraint_name(border_name, time_index),
                    )

    def create_borders_constraints(self):
        for time_index, time in enumerate(self.input_dataset.times):
            for border_name, mc_border in self.input_dataset.mc_market_borders.items():
                if mc_border.loss_factor <= 0.0:
                    continue
                relative_max_flow = mc_border.max_flow.get_value(time)
                relative_min_flow = mc_border.min_flow.get_value(time)
                timed_export = self.get_variable(constants.border_export_variable_name(border_name, time_index))
                timed_import = self.get_variable(constants.border_import_variable_name(border_name, time_index))
                timed_xsis = self.get_variable(constants.border_xsis_variable_name(border_name, time_index))
                timed_nus = self.get_variable(constants.border_nus_variable_name(border_name, time_index))

                self.add_constraint(
                    relative_min_flow <= 0.5 * (timed_import + timed_export),
                    constants.constraint_4_4a_min_constraint_name(border_name, time_index),
                )
                self.add_constraint(
                    relative_max_flow >= 0.5 * (timed_import + timed_export),
                    constants.constraint_4_4a_max_constraint_name(border_name, time_index),
                )

                import_after_losses = (
                    (1.0 - mc_border.loss_factor) - 1.0 / (1.0 - mc_border.loss_factor)
                ) * timed_xsis + timed_export / (1.0 - mc_border.loss_factor)
                self.add_constraint(
                    timed_import >= import_after_losses,
                    constants.constraint_4_3a_constraint_name(border_name, time_index),
                )

                self.add_constraint(
                    timed_nus * relative_min_flow <= timed_xsis,
                    constants.constraint_4_3d_min_constraint_name(border_name, time_index),
                )
                self.add_constraint(
                    timed_nus * relative_max_flow >= timed_xsis,
                    constants.constraint_4_3d_max_constraint_name(border_name, time_index),
                )

                self.add_constraint(
                    (1 - timed_nus) * relative_min_flow <= timed_export - timed_xsis,
                    constants.constraint_4_3e_min_constraint_name(border_name, time_index),
                )
                self.add_constraint(
                    (1 - timed_nus) * relative_max_flow >= timed_export - timed_xsis,
                    constants.constraint_4_3e_max_constraint_name(border_name, time_index),
                )

    def get_n_borders_with_losses(self):
        n_borders_with_losses = 0
        for mc_market_border in self.input_dataset.mc_market_borders.values():
            if mc_market_border.loss_factor and mc_market_border.loss_factor > 0.0:
                n_borders_with_losses += 1
        return n_borders_with_losses

    def get_border_exchanges(self) -> dict[tuple[str, int], float]:
        """
        :rtype: dict[tuple[str, str], float]
        """
        border_exchanges = {}
        for time_index, _ in enumerate(self.input_dataset.times):
            for border_name in self.input_dataset.mc_market_borders.keys():
                border_exchange_name = constants.border_exchange_variable_name(border_name, time_index)
                border_exchanges[border_name, time_index] = self.get_variable(border_exchange_name).solution_value()
        return border_exchanges
