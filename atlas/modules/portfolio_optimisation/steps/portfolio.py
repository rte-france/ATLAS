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
    from atlas.solver.temporal_variable import TemporalVariable

#: Portfolio-level variables measuring the reserves the portfolio fails to procure.
CONTRACT_DIFFERENCES = [
    "contracted_diff_up",
    "contracted_diff_down",
    "automated_contracted_diff_up",
    "automated_contracted_diff_down",
]


class PortfolioStep:
    """
    Portfolio-level part of the optimisation: imbalance and reserve procurement.

    Owns the imbalance and contract-difference temporal variables and reads the power and
    reserves of each equipment through its step, never through solver variable names.
    """

    def __init__(self, portfolio: PortfolioPO):
        self.portfolio = portfolio
        self._equipment_steps = [
            create_po_step(equipment)
            for _, equipment_list in portfolio.equipments.iter_by_type_for_optimisation()
            for equipment in equipment_list
        ]
        self._steps_by_equipment = {step.equipment.name: step for step in self._equipment_steps}

        self.small_imbalance_up: TemporalVariable = None  # type: ignore[assignment]
        self.small_imbalance_down: TemporalVariable = None  # type: ignore[assignment]
        self.large_imbalance_up: TemporalVariable = None  # type: ignore[assignment]
        self.large_imbalance_down: TemporalVariable = None  # type: ignore[assignment]
        self.contract_differences: dict[str, TemporalVariable] = {}

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters) -> None:
        portfolio = self.portfolio
        cfg.logger.debug(f"Adding variables for portfolio :{portfolio.name}")
        self._add_imbalance_variables(model, parameters)
        self._add_contract_difference_variables(model, parameters)

        for step in self._equipment_steps:
            step.add_variables(model, parameters)

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters) -> None:
        portfolio = self.portfolio
        for step in self._equipment_steps:
            step.add_constraints(model, parameters)

        for time in parameters.portfolio_time_window:
            cfg.logger.debug(f"Adding constraints for portfolio :{portfolio.name}")
            self._add_global_constraints(time, model, parameters)
            if portfolio.equipments.has_generation_equipment():
                self._add_reserves_constraints(time, model, parameters)

    def add_objective(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters) -> None:
        portfolio = self.portfolio
        all_times: set[DateTime] = set(parameters.portfolio_time_window)
        for step in self._equipment_steps:
            all_times.update(parameters.equipment_time_window(step.equipment))

        price_forecasts = {time: portfolio.get_price_forecast(time, parameters) or 0.0 for time in all_times}

        for step in self._equipment_steps:
            step.add_objective(model, parameters, price_forecasts)

        for time in sorted(parameters.portfolio_time_window):
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
                getattr(self._steps_by_equipment[obj.name].reserves, reserve_type)[time]
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
            model.add_constraint(self.contract_differences[var_name][time] >= target - sum_var, constrainte_name)

    def _add_global_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ) -> None:
        portfolio = self.portfolio
        residual_energy = portfolio._compute_residual_energy(time, parameters)
        max_overall_imbal = max(residual_energy, parameters.maximum_imbalance)
        sum_power_variables = self._get_sum_power_level_variables(time, parameters)
        small_imbalance_up_var = self.small_imbalance_up[time]
        large_imbalance_up_var = self.large_imbalance_up[time]
        small_imbalance_down_var = self.small_imbalance_down[time]
        large_imbalance_down_var = self.large_imbalance_down[time]

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

    def _add_imbalance_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters) -> None:
        portfolio = self.portfolio
        window = parameters.portfolio_time_window
        small_limit: dict[DateTime, float] = {}
        overall_limit: dict[DateTime, float] = {}
        for time in window:
            residual_energy = portfolio._compute_residual_energy(time, parameters)
            maximum_power = portfolio._compute_maximum_power(time, parameters)
            small_limit[time] = maximum_power * parameters.small_imbalance_size
            overall_limit[time] = max(residual_energy, parameters.maximum_imbalance)

        def imbalance(name: str, limit: dict[DateTime, float]) -> TemporalVariable:
            return model.add_temporal_variable(
                f"{portfolio.name}_{name}", window, lower_bound=0, upper_bound=limit.__getitem__
            )

        self.small_imbalance_up = imbalance("small_imbalance_up", small_limit)
        self.small_imbalance_down = imbalance("small_imbalance_down", small_limit)
        self.large_imbalance_up = imbalance("large_imbalance_up", overall_limit)
        self.large_imbalance_down = imbalance("large_imbalance_down", overall_limit)

    def _add_contract_difference_variables(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ) -> None:
        portfolio = self.portfolio
        maximum_power = {
            time: portfolio._compute_maximum_power(time, parameters) for time in parameters.portfolio_time_window
        }
        self.contract_differences = {
            name: model.add_temporal_variable(
                f"{name}_{portfolio.name}",
                parameters.portfolio_time_window,
                lower_bound=0,
                upper_bound=maximum_power.__getitem__,
            )
            for name in CONTRACT_DIFFERENCES
        }

    def _get_sum_power_level_variables(self, time: DateTime, parameters: PortfolioOptimisationParameters) -> float:
        portfolio = self.portfolio
        total_power = 0
        for obj in (
            portfolio.equipments.storage
            + portfolio.equipments.hydro
            + portfolio.equipments.thermal
            + portfolio.equipments.wind
            + portfolio.equipments.solar
            + portfolio.equipments.dispatchable_load
        ):
            if time in parameters.equipment_time_window(obj):
                total_power += self._steps_by_equipment[obj.name].power_level(time)
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
        small_imbalance_up_var = self.small_imbalance_up[time]
        small_imbalance_down_var = self.small_imbalance_down[time]
        large_imbalance_up_var = self.large_imbalance_up[time]
        large_imbalance_down_var = self.large_imbalance_down[time]

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
        contracted_diff_up = self.contract_differences["contracted_diff_up"][time]
        contracted_diff_down = self.contract_differences["contracted_diff_down"][time]
        auto_contracted_diff_up = self.contract_differences["automated_contracted_diff_up"][time]
        auto_contracted_diff_down = self.contract_differences["automated_contracted_diff_down"][time]

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
