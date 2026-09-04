"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import json

import pendulum

import atlas.modules.market_clearing.constants as constants
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases import _border_variables
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel


class ExchangesFixing:
    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        solver_options = SolverOptions(presolve=parameters.solver.use_presolve)

        self.model = OptimisationModel(parameters.solver.solver_name, options=solver_options, name="ExchangesFixing")
        self.input_dataset = input_dataset
        self.parameters = parameters

    def compute(self, clearing_local_balances: dict[tuple[str, pendulum.DateTime], float]):
        self.build(clearing_local_balances)
        self.model.solve()
        if self.parameters.solver.export_lp:
            output_path = self.parameters.get_lp_dir()
            output_path.mkdir(parents=True, exist_ok=True)
            self.model.export_model(output_path / "exchanges_fixing_model.lp")

            with open(output_path / "exchanges_fixing_border_exchanges.json", "w") as f:
                json.dump(
                    [[b, str(t), val] for (b, t), val in self.get_border_exchanges().items()],
                    f,
                )

    def build(self, clearing_local_balances: dict[tuple[str, pendulum.DateTime], float]):
        self.build_variables()
        self.build_constraints(clearing_local_balances)
        self.build_objective()

    def build_variables(self):
        """Create all variables for the exchange fixing phase model"""
        is_atc = self.input_dataset.is_atc

        _border_variables.create_border_exchange_variables(self, is_atc)
        _border_variables.create_border_pos_exchanges_variables(self, is_atc)
        _border_variables.create_border_neg_exchanges_variables(self, is_atc)

        if is_atc:
            _border_variables.create_border_loss_variables(
                self, constants.border_import_variable_name, only_borders_with_losses=False
            )
            _border_variables.create_border_loss_variables(
                self, constants.border_export_variable_name, only_borders_with_losses=False
            )
            _border_variables.create_border_loss_variables(
                self, constants.border_xsis_variable_name, only_borders_with_losses=False
            )
            _border_variables.create_border_loss_variables(
                self, constants.border_nus_variable_name, only_borders_with_losses=False
            )

    def build_constraints(self, clearing_local_balances: dict[tuple[str, pendulum.DateTime], float]):
        """Create all constraints for the exchange fixing phase model"""
        is_atc = self.input_dataset.is_atc
        self.create_exchanges_constraints(is_atc, clearing_local_balances)
        self.create_absolute_timed_exchanges_constraints(is_atc)
        if is_atc and self.get_n_borders_with_losses():
            self.create_borders_constraints()

    def build_objective(self):
        """Create objective function for the exchanges fixing phase model"""
        objective = []
        for border_name in self.input_dataset.market_borders.keys():
            for time in self.input_dataset.times:
                border_pos_exchange = self.model.get_variable(
                    constants.border_pos_exchange_variable_name(border_name, time)
                )
                border_neg_exchange = self.model.get_variable(
                    constants.border_neg_exchange_variable_name(border_name, time)
                )
                objective.append(border_pos_exchange - border_neg_exchange)
        self.model.set_direction("maximize")
        self.model.add_objective(sum(objective))

    ##################################
    # Constraints
    ##################################
    def create_exchanges_constraints(
        self, is_atc: bool, clearing_local_balances: dict[tuple[str, pendulum.DateTime], float]
    ):
        for time in self.input_dataset.times:
            for market_area_name in self.input_dataset.market_areas:
                if is_atc:
                    exchange_sum = self.compute_atc_exchange_sum_for_market_area(market_area_name, time)
                else:
                    exchange_sum = self.compute_fb_exchange_sum_for_market_area(market_area_name, time)
                constraint_name = constants.constraint_4_2_constraint_name(market_area_name, time)
                clearing_exchange_value = clearing_local_balances[market_area_name, time]
                self.model.add_constraint(clearing_exchange_value == exchange_sum, constraint_name)

    def compute_atc_exchange_sum_for_market_area(self, market_area_name: str, time: pendulum.DateTime):
        """Compute the sum of exchange in a market area when atc"""
        exchanges_sum = []
        for border_name, border in self.input_dataset.market_borders.items():
            if market_area_name not in [
                border.uphill_market_area.name,
                border.downhill_market_area.name,
            ]:
                continue
            if border.loss_factor != 0.0:
                if border.uphill_market_area.name == market_area_name:
                    exchanges_sum.append(
                        self.model.get_variable(constants.border_export_variable_name(border_name, time))
                    )
                elif border.downhill_market_area.name == market_area_name:
                    exchanges_sum.append(
                        -self.model.get_variable(constants.border_import_variable_name(border_name, time))
                    )
            else:
                border_sign = 1 if market_area_name == border.uphill_market_area.name else -1
                exchanges_sum.append(
                    border_sign * self.model.get_variable(constants.border_exchange_variable_name(border_name, time))
                )
        return sum(exchanges_sum)

    def compute_fb_exchange_sum_for_market_area(self, market_area_name: str, time: pendulum.DateTime):
        """Compute the sum of exchange in a market area when fb"""
        exchanges_sum = []
        for border_name, border in self.input_dataset.market_borders.items():
            if market_area_name not in [
                border.uphill_market_area.name,
                border.downhill_market_area.name,
            ]:
                continue
            border_sign = 1 if market_area_name == border.uphill_market_area.name else -1
            exchanges_sum.append(
                border_sign * self.model.get_variable(constants.border_exchange_variable_name(border_name, time))
            )
        return sum(exchanges_sum)

    def create_absolute_timed_exchanges_constraints(self, is_atc: bool):
        for time in self.input_dataset.times:
            for border_name, border in self.input_dataset.market_borders.items():
                timed_pos_exchanges = self.model.get_variable(
                    constants.border_pos_exchange_variable_name(border_name, time)
                )
                timed_neg_exchanges = self.model.get_variable(
                    constants.border_neg_exchange_variable_name(border_name, time)
                )
                # Compute the sum of the absolute values of exchanges:
                if is_atc and border.loss_factor != 0.0:
                    timed_exports = self.model.get_variable(constants.border_export_variable_name(border_name, time))
                    timed_imports = self.model.get_variable(constants.border_import_variable_name(border_name, time))
                    self.model.add_constraint(
                        timed_pos_exchanges + timed_neg_exchanges == 0.5 * (timed_imports + timed_exports),
                        constants.absolute_timed_exchanges_constraint_name(border_name, time),
                    )
                else:
                    timed_exchanges = self.model.get_variable(
                        constants.border_exchange_variable_name(border_name, time)
                    )
                    self.model.add_constraint(
                        timed_pos_exchanges + timed_neg_exchanges == timed_exchanges,
                        constants.absolute_timed_exchanges_constraint_name(border_name, time),
                    )

    def create_borders_constraints(self):
        timestep_minutes = self.parameters.temporal.timestep.total_minutes()
        for time in self.input_dataset.times:
            for border_name, border in self.input_dataset.market_borders.items():
                if border.loss_factor <= 0.0 or not border.loss_factor:
                    continue
                relative_max_flow = border.max_flow.get_value(time)
                relative_min_flow = border.min_flow.get_value(time)
                timed_export = self.model.get_variable(constants.border_export_variable_name(border_name, time))
                timed_import = self.model.get_variable(constants.border_import_variable_name(border_name, time))
                timed_xsis = self.model.get_variable(constants.border_xsis_variable_name(border_name, time))
                timed_nus = self.model.get_variable(constants.border_nus_variable_name(border_name, time))

                self.model.add_constraint(
                    relative_min_flow <= 0.5 * (timed_import + timed_export),
                    constants.constraint_4_4a_min_constraint_name(border_name, time),
                )
                self.model.add_constraint(
                    relative_max_flow >= 0.5 * (timed_import + timed_export),
                    constants.constraint_4_4a_max_constraint_name(border_name, time),
                )

                tmp_rhs = (
                    (1.0 - border.loss_factor) - 1.0 / (1.0 - border.loss_factor)
                ) * timed_xsis + timed_export / (1.0 - border.loss_factor)

                self.model.add_constraint(
                    timed_import == tmp_rhs, constants.constraint_4_3a_constraint_name(border_name, time)
                )

                self.model.add_constraint(
                    timed_xsis >= 0.5 * timed_export,
                    constants.constraint_4_3b_constraint_name(border_name, time),
                )

                self.model.add_constraint(
                    timed_nus * relative_min_flow <= timed_xsis,
                    constants.constraint_4_3d_min_constraint_name(border_name, time),
                )
                self.model.add_constraint(
                    timed_nus * relative_max_flow >= timed_xsis,
                    constants.constraint_4_3d_max_constraint_name(border_name, time),
                )

                self.model.add_constraint(
                    (1 - timed_nus) * relative_min_flow <= timed_export - timed_xsis,
                    constants.constraint_4_3e_min_constraint_name(border_name, time),
                )
                self.model.add_constraint(
                    (1 - timed_nus) * relative_max_flow >= timed_export - timed_xsis,
                    constants.constraint_4_3e_max_constraint_name(border_name, time),
                )

                # Compute the constraint (4.5) that considers the time
                # resolution of exchanges across the border:
                if border.time_resolution is not None and border.resolution_time > timestep_minutes:
                    minutes_elapsed = (time - self.parameters.temporal.start_date).in_minutes()
                    minutes_into_block = minutes_elapsed % border.resolution_time
                    if minutes_into_block:
                        block_start = time.subtract(minutes=minutes_into_block)
                        self.model.add_constraint(
                            self.model.get_variable(constants.border_exchange_variable_name(border_name, time))
                            == self.model.get_variable(
                                constants.border_exchange_variable_name(border_name, block_start)
                            ),
                            constants.border_exchanges_constraint_name(border_name, time),
                        )

    def get_n_borders_with_losses(self):
        n_borders_with_losses = 0
        for border in self.input_dataset.market_borders.values():
            if border.loss_factor and border.loss_factor > 0.0:
                n_borders_with_losses += 1
        return n_borders_with_losses

    def get_border_exchanges(self) -> dict[tuple[str, pendulum.DateTime], float]:
        """
        :rtype: dict[tuple[str, str], float]
        """
        border_exchanges = {}
        for time in self.input_dataset.times:
            for border_name in self.input_dataset.market_borders.keys():
                border_exchange_name = constants.border_exchange_variable_name(border_name, time)
                border_exchanges[border_name, time] = self.model.get_variable(border_exchange_name).solution_value()
        return border_exchanges
