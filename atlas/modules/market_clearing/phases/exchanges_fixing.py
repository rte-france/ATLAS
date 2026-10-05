"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import json
from typing import Any

import pendulum

from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases._border_variables import (
    add_absolute_exchanges,
    add_exchange_variables,
    add_loss_variables,
)
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel


class ExchangesFixing:
    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        solver_options = SolverOptions(presolve=parameters.solver.use_presolve)

        self.model = OptimisationModel(parameters.solver.solver_name, options=solver_options, name="ExchangesFixing")
        self.input_dataset = input_dataset
        self.parameters = parameters

        # Variables only depend on the inputs: they are declared here so that the phase is complete once built
        self.exchange = add_exchange_variables(self.model, input_dataset)
        self.absolute = add_absolute_exchanges(self.model, input_dataset)
        self.losses = add_loss_variables(self.model, input_dataset, only_borders_with_losses=False)

    def compute(self, clearing_local_balances: dict[str, Timeseries]) -> None:
        self.build(clearing_local_balances)
        self.model.solve()
        if self.parameters.solver.export_lp:
            output_path = self.parameters.lp_dir
            output_path.mkdir(parents=True, exist_ok=True)
            self.model.export_model(output_path / "exchanges_fixing_model.lp")

            with open(output_path / "exchanges_fixing_border_exchanges.json", "w") as f:
                json.dump(
                    [
                        [b, str(t), val]
                        for b, exchange in self.get_border_exchanges().items()
                        for t, val in exchange.iter_rows()
                    ],
                    f,
                )

    def build(self, clearing_local_balances: dict[str, Timeseries]) -> None:
        self.build_constraints(clearing_local_balances)
        self.build_objective()

    def build_constraints(self, clearing_local_balances: dict[str, Timeseries]) -> None:
        """Create all constraints for the exchange fixing phase model"""
        is_atc = self.input_dataset.is_atc
        self.create_balance_exchange_constraints(is_atc, clearing_local_balances)
        self.create_absolute_exchange_constraints(is_atc)
        if is_atc:
            self.create_loss_constraints()

    def build_objective(self) -> None:
        """Create objective function for the exchanges fixing phase model"""
        objective = []
        for border_name in self.input_dataset.market_borders.keys():
            for time in self.input_dataset.times:
                border_pos_exchange = self.absolute.positive[border_name][time]
                border_neg_exchange = self.absolute.negative[border_name][time]
                objective.append(border_pos_exchange - border_neg_exchange)
        self.model.set_direction("maximize")
        self.model.add_objective(sum(objective))

    ##################################
    # Constraints
    ##################################
    def create_balance_exchange_constraints(self, is_atc: bool, clearing_local_balances: dict[str, Timeseries]) -> None:
        for time in self.input_dataset.times:
            for market_area_name in self.input_dataset.market_areas:
                net_export = (
                    self.atc_net_export(market_area_name, time)
                    if is_atc
                    else self.fb_net_export(market_area_name, time)
                )
                self.model.add_constraint(
                    clearing_local_balances[market_area_name].get_value(time) == net_export,
                    f"Constraint_4.2_at_time_{time}_on_market_area_{market_area_name}",
                )

    def atc_net_export(self, market_area_name: str, time: pendulum.DateTime) -> Any:
        """Net export of a market area in ATC, after losses on the borders with a loss factor (exported uphill,
        imported downhill)."""
        exchanges_sum = []
        for border_name, border in self.input_dataset.market_borders.items():
            if market_area_name not in [
                border.uphill_market_area.name,
                border.downhill_market_area.name,
            ]:
                continue
            if border.loss_factor != 0.0:
                if border.uphill_market_area.name == market_area_name:
                    exchanges_sum.append(self.losses[border_name].exports[time])
                elif border.downhill_market_area.name == market_area_name:
                    exchanges_sum.append(-self.losses[border_name].imports[time])
            else:
                border_sign = 1 if market_area_name == border.uphill_market_area.name else -1
                exchanges_sum.append(border_sign * self.exchange[border_name][time])
        return sum(exchanges_sum)

    def fb_net_export(self, market_area_name: str, time: pendulum.DateTime) -> Any:
        """Net export of a market area in flow-based: the exchanges on its borders, positive uphill."""
        exchanges_sum = []
        for border_name, border in self.input_dataset.market_borders.items():
            if market_area_name not in [
                border.uphill_market_area.name,
                border.downhill_market_area.name,
            ]:
                continue
            border_sign = 1 if market_area_name == border.uphill_market_area.name else -1
            exchanges_sum.append(border_sign * self.exchange[border_name][time])
        return sum(exchanges_sum)

    def create_absolute_exchange_constraints(self, is_atc: bool) -> None:
        for time in self.input_dataset.times:
            for border_name, border in self.input_dataset.market_borders.items():
                positive_exchange = self.absolute.positive[border_name][time]
                negative_exchange = self.absolute.negative[border_name][time]
                # Compute the sum of the absolute values of exchanges:
                if is_atc and border.loss_factor != 0.0:
                    exports = self.losses[border_name].exports[time]
                    imports = self.losses[border_name].imports[time]
                    self.model.add_constraint(
                        positive_exchange + negative_exchange == 0.5 * (imports + exports),
                        f"Positive_and_negative_parts_definition_at_time_{time}_on_market_border_{border_name}",
                    )
                else:
                    exchange = self.exchange[border_name][time]
                    self.model.add_constraint(
                        positive_exchange + negative_exchange == exchange,
                        f"Positive_and_negative_parts_definition_at_time_{time}_on_market_border_{border_name}",
                    )

    def create_loss_constraints(self) -> None:
        timestep_minutes = self.parameters.temporal.timestep.total_minutes()
        for time in self.input_dataset.times:
            for border_name, border in self.input_dataset.market_borders.items():
                if not border.loss_factor or border.loss_factor <= 0.0:
                    continue
                loss_factor = border.loss_factor
                relative_max_flow = border.max_flow.get_value(time)
                relative_min_flow = border.min_flow.get_value(time)
                losses = self.losses[border_name]
                exports = losses.exports[time]
                imports = losses.imports[time]
                xsis = losses.xsis[time]
                nus = losses.nus[time]

                self.model.add_constraint(
                    relative_min_flow <= 0.5 * (imports + exports),
                    f"Constraint_4.4a_(min)_at_time_{time}_on_market_border_{border_name}",
                )
                self.model.add_constraint(
                    relative_max_flow >= 0.5 * (imports + exports),
                    f"Constraint_4.4a_(max)_at_time_{time}_on_market_border_{border_name}",
                )

                import_after_losses = ((1.0 - loss_factor) - 1.0 / (1.0 - loss_factor)) * xsis + exports / (
                    1.0 - loss_factor
                )

                self.model.add_constraint(
                    imports == import_after_losses, f"Constraint_4.3a_at_time_{time}_on_market_border_{border_name}"
                )

                self.model.add_constraint(
                    xsis >= 0.5 * exports,
                    f"Constraint_4.3b_at_time_{time}_on_market_border_{border_name}",
                )

                self.model.add_constraint(
                    nus * relative_min_flow <= xsis,
                    f"Constraint_4.3d_(min)_at_time_{time}_on_market_border {border_name}",
                )
                self.model.add_constraint(
                    nus * relative_max_flow >= xsis,
                    f"Constraint_4.3d_(max)_at_time_{time}_on_market_border_{border_name}",
                )

                self.model.add_constraint(
                    (1 - nus) * relative_min_flow <= exports - xsis,
                    f"Constraint_4.3e_(min)_at_time_{time}_on_market_border_{border_name}",
                )
                self.model.add_constraint(
                    (1 - nus) * relative_max_flow >= exports - xsis,
                    f"Constraint_4.3e_(max)_at_time_{time}_on_market_border_{border_name}",
                )

                # Compute the constraint (4.5) that considers the time
                # resolution of exchanges across the border:
                if border.time_resolution is not None and border.resolution_time > timestep_minutes:
                    minutes_elapsed = (time - self.parameters.temporal.start_date).in_minutes()
                    minutes_into_block = minutes_elapsed % border.resolution_time
                    if minutes_into_block:
                        block_start = time.subtract(minutes=minutes_into_block)
                        exchange = self.exchange[border_name]
                        self.model.add_constraint(
                            exchange[time] == exchange[block_start],
                            f"Constraint_4.5_at_time_{time}_on_market_border_{border_name}",
                        )

    def get_border_exchanges(self) -> dict[str, Timeseries]:
        """Retrieve the exchange on each market border over the clearing horizon

        :rtype: dict[str, Timeseries]
        """
        return {border_name: exchange.solution() for border_name, exchange in self.exchange.items()}
