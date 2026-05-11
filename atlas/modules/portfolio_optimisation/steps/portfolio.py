"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.modules.portfolio_optimisation.input_objects.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.steps import create_po_step
from atlas.modules.portfolio_optimisation.utils.imbalance_price import estimate_imbalance_prices
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from pendulum import DateTime, Duration

    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class PortfolioStep:
    def __init__(self, portfolio: PortfolioPO):
        self.portfolio = portfolio
        self._equipment_steps = [
            create_po_step(equipment)
            for _, equipment_list in portfolio.equipments.iter_by_type_for_optimisation()
            for equipment in equipment_list
        ]

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters) -> None:
        portfolio = self.portfolio
        for time in parameters.target_times:
            cfg.logger.debug(f"Adding variables for portfolio :{portfolio.name} at time {time}")
            residual_energy = portfolio._compute_residual_energy(time, parameters)
            maximum_power = portfolio._compute_maximum_power(time, parameters)
            self._add_imbalance_variables(model, time, residual_energy, maximum_power, parameters)
            self._add_contract_difference_variables(model, time, maximum_power)

        for step in self._equipment_steps:
            step.add_variables(model, parameters)

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters) -> None:
        portfolio = self.portfolio
        for step in self._equipment_steps:
            step.add_constraints(model, parameters)

        for time in parameters.target_times:
            cfg.logger.debug(f"Adding constraints for portfolio :{portfolio.name}")
            self._add_global_constraints(time, model, parameters)
            if portfolio.equipments.has_generation_equipment():
                self._add_reserves_constraints(time, model, parameters)

    def add_objective(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters) -> None:
        portfolio = self.portfolio
        all_times: set[DateTime] = set(parameters.target_times)
        for step in self._equipment_steps:
            all_times.update(step.equipment.optimisation_time_window)

        price_forecasts = {time: portfolio.get_price_forecast(time, parameters) or 0.0 for time in all_times}

        for step in self._equipment_steps:
            step.add_objective(model, parameters, price_forecasts)

        for time in sorted(parameters.target_times):
            cfg.logger.debug(f"Adding objective terms for portfolio :{portfolio.name} at time {time}")
            imbalance_prices = estimate_imbalance_prices(
                time, portfolio.market_area, portfolio.control_block, parameters
            )
            self._add_imbalance_cost_terms(model, time, *imbalance_prices, parameters.temporal.timestep)
            if portfolio.equipments.has_generation_equipment():
                self._add_reserve_penalty_terms(model, time, parameters)

    def _add_reserves_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ) -> None:
        portfolio = self.portfolio

        def sum_reserve_vars(reserve_type: str) -> float:
            return sum(
                model.get_variable(f"{reserve_type}_{obj.name}_{time}")
                for _, equipment_list in portfolio.equipments.get_reserve_equipment_types()
                for obj in equipment_list
            )

        reserve_types = ["reserves_up", "reserves_down", "automated_reserves_up", "automated_reserves_down"]
        sum_reserves = {r_type: sum_reserve_vars(r_type) for r_type in reserve_types}

        reserves_up, reserves_down, automated_reserves_up, automated_reserves_down = portfolio._compute_reserves_time(
            time, parameters
        )

        constraints_config = [
            ("contracted_diff_up", reserves_up, sum_reserves["reserves_up"], f"reserves_balance_up_{time}"),
            ("contracted_diff_down", reserves_down, sum_reserves["reserves_down"], f"reserves_balance_down_{time}"),
            (
                "automated_contracted_diff_up",
                automated_reserves_up,
                sum_reserves["automated_reserves_up"],
                f"automated_reserves_balance_up_{time}",
            ),
            (
                "automated_contracted_diff_down",
                automated_reserves_down,
                sum_reserves["automated_reserves_down"],
                f"automated_reserves_balance_down_{time}",
            ),
        ]

        for var_name, target, sum_var, constrainte_name in constraints_config:
            model.add_constraint(
                model.get_variable(f"{var_name}_{portfolio.name}_{time}") >= target - sum_var, constrainte_name
            )

    def _add_global_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ) -> None:
        portfolio = self.portfolio
        residual_energy = portfolio._compute_residual_energy(time, parameters)
        max_overall_imbal = max(residual_energy, parameters.maximum_imbalance)
        sum_power_variables = self._get_sum_power_level_variables(model, time)
        small_imbalance_up_var = model.get_variable(f"{portfolio.name}_small_imbalance_up_{time}")
        large_imbalance_up_var = model.get_variable(f"{portfolio.name}_large_imbalance_up_{time}")
        small_imbalance_down_var = model.get_variable(f"{portfolio.name}_small_imbalance_down_{time}")
        large_imbalance_down_var = model.get_variable(f"{portfolio.name}_large_imbalance_down_{time}")

        model.add_constraint(
            small_imbalance_up_var + large_imbalance_up_var - small_imbalance_down_var - large_imbalance_down_var
            == residual_energy - sum_power_variables,
            name=f"portfolio_balance_{time}",
        )
        model.add_constraint(
            (small_imbalance_up_var + large_imbalance_up_var <= max_overall_imbal),
            name=f"up_imbalance_limit_{time}",
        )
        model.add_constraint(
            (small_imbalance_down_var + large_imbalance_down_var <= max_overall_imbal),
            name=f"down_imbalance_limit_{time}",
        )

    def _add_imbalance_variables(
        self,
        model: OptimisationModel,
        time: DateTime,
        residual_energy: float,
        maximum_power: float,
        parameters: PortfolioOptimisationParameters,
    ) -> None:
        portfolio = self.portfolio
        small_imbalance_limit = maximum_power * parameters.small_imbalance_size
        max_overall_imbal = max(residual_energy, parameters.maximum_imbalance)

        model.add_continuous_variable(
            name=f"{portfolio.name}_small_imbalance_up_{time}", lower_bound=0, upper_bound=small_imbalance_limit
        )
        model.add_continuous_variable(
            name=f"{portfolio.name}_small_imbalance_down_{time}", lower_bound=0, upper_bound=small_imbalance_limit
        )
        model.add_continuous_variable(
            name=f"{portfolio.name}_large_imbalance_up_{time}", lower_bound=0, upper_bound=max_overall_imbal
        )
        model.add_continuous_variable(
            name=f"{portfolio.name}_large_imbalance_down_{time}", lower_bound=0, upper_bound=max_overall_imbal
        )

    def _add_contract_difference_variables(
        self, model: OptimisationModel, time: DateTime, maximum_power: float
    ) -> None:
        portfolio = self.portfolio
        for v in [
            "contracted_diff_up",
            "contracted_diff_down",
            "automated_contracted_diff_up",
            "automated_contracted_diff_down",
        ]:
            model.add_continuous_variable(name=f"{v}_{portfolio.name}_{time}", lower_bound=0, upper_bound=maximum_power)

    def _get_sum_power_level_variables(self, model: OptimisationModel, time: DateTime) -> float:
        portfolio = self.portfolio
        total_power = 0

        for storage in portfolio.equipments.storage:
            if time in storage.optimisation_time_window:
                total_power += model.get_variable(f"{storage.name}_power_level_sell_{time}")
                total_power += model.get_variable(f"{storage.name}_power_level_buy_{time}")

        for hydro in portfolio.equipments.hydro:
            if time in hydro.optimisation_time_window:
                for category in hydro.fragment_data.keys():
                    total_power += model.get_variable(f"{hydro.name}_power_level_frag_{category}_{time}")

        for obj in (
            portfolio.equipments.thermal
            + portfolio.equipments.wind
            + portfolio.equipments.solar
            + portfolio.equipments.dispatchable_load
        ):
            if time in obj.optimisation_time_window:
                total_power += model.get_variable(f"{obj.name}_power_level_{time}")

        return total_power

    def _add_imbalance_cost_terms(
        self,
        model: OptimisationModel,
        time: DateTime,
        imbalance_price_down: float,
        imbalance_price_up: float,
        large_imbalance_price_down: float,
        large_imbalance_price_up: float,
        timestep: Duration,
    ) -> None:
        portfolio = self.portfolio
        small_imbalance_up_var = model.get_variable(f"{portfolio.name}_small_imbalance_up_{time}")
        small_imbalance_down_var = model.get_variable(f"{portfolio.name}_small_imbalance_down_{time}")
        large_imbalance_up_var = model.get_variable(f"{portfolio.name}_large_imbalance_up_{time}")
        large_imbalance_down_var = model.get_variable(f"{portfolio.name}_large_imbalance_down_{time}")

        if imbalance_price_up:
            model.add_objective(imbalance_price_up * small_imbalance_up_var * timestep.total_hours())
        if imbalance_price_down:
            model.add_objective(-imbalance_price_down * small_imbalance_down_var * timestep.total_hours())
        if large_imbalance_price_up:
            model.add_objective(large_imbalance_price_up * large_imbalance_up_var * timestep.total_hours())
        if large_imbalance_price_down:
            model.add_objective(-large_imbalance_price_down * large_imbalance_down_var * timestep.total_hours())

    def _add_reserve_penalty_terms(
        self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters
    ) -> None:
        portfolio = self.portfolio
        contracted_diff_up = model.get_variable(f"contracted_diff_up_{portfolio.name}_{time}")
        contracted_diff_down = model.get_variable(f"contracted_diff_down_{portfolio.name}_{time}")
        auto_contracted_diff_up = model.get_variable(f"automated_contracted_diff_up_{portfolio.name}_{time}")
        auto_contracted_diff_down = model.get_variable(f"automated_contracted_diff_down_{portfolio.name}_{time}")

        model.add_objective(
            parameters.manual_unprocured_reserves_penalty
            * parameters.temporal.timestep.total_hours()
            * contracted_diff_up
        )
        model.add_objective(
            parameters.manual_unprocured_reserves_penalty
            * parameters.temporal.timestep.total_hours()
            * contracted_diff_down
        )
        model.add_objective(
            parameters.automated_unprocured_reserves_penalty
            * parameters.temporal.timestep.total_hours()
            * auto_contracted_diff_up
        )
        model.add_objective(
            parameters.automated_unprocured_reserves_penalty
            * parameters.temporal.timestep.total_hours()
            * auto_contracted_diff_down
        )
