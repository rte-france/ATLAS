"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import cast

from pendulum import DateTime, Duration

import atlas.config as cfg
from atlas.enum import MarketType
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.models.control_block import ControlBlockPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.market_area import MarketAreaPO
from atlas.modules.portfolio_optimisation.models.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.models.portfolio_equipments import PortfolioEquipments
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_power, get_reserve, get_upstream_energy
from atlas.modules.portfolio_optimisation.utils.imbalance_price import estimate_imbalance_prices
from atlas.solver.solver_interface import OptimisationModel


class PortfolioPO(Portfolio):
    market_area: MarketAreaPO
    control_block: ControlBlockPO
    equipments: PortfolioEquipments

    def add_variables(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ):
        """Build portfolio-level optimization variables."""

        if time in parameters.target_times:
            cfg.logger.debug(f"Adding variables for portfolio :{self.name} at time {time}")
            residual_energy = self._compute_residual_energy(time, parameters)
            maximum_power = self._compute_maximum_power(time, parameters)

            self._add_imbalance_variables(model, time, residual_energy, maximum_power, parameters)
            self._add_contract_difference_variables(model, time, maximum_power)
        else:
            cfg.logger.debug(f"Skipping variables adding for portfolio :{self.name} at non-target time {time}")

    def add_constraints(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        if time in parameters.target_times:
            cfg.logger.debug(f"Adding constraints for portfolio :{self.name}")
            self._add_global_constraints(time, model, parameters)
            if self.equipments.has_generation_equipment():
                self._add_reserves_constraints(time, model, parameters)
        else:
            cfg.logger.debug(f"Skipping constraints for portfolio :{self.name} at non-target time {time}")

    def _add_reserves_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        def sum_reserve_vars(reserve_type: str) -> float:
            return sum(
                model.get_variable(f"{reserve_type}_{obj.name}_{time}")
                for _, equipment_list in self.equipments.get_reserve_equipment_types()
                for obj in equipment_list
            )

        # Compute all reserve sums
        reserve_types = ["reserves_up", "reserves_down", "automated_reserves_up", "automated_reserves_down"]
        sum_reserves = {r_type: sum_reserve_vars(r_type) for r_type in reserve_types}

        # Get target reserve values
        reserves_up, reserves_down, automated_reserves_up, automated_reserves_down = self._compute_reserves_time(
            time, parameters
        )

        # Map reserve types to their target values and contracted variable names
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

        # Add all constraints
        for var_name, target, sum_var, constrainte_name in constraints_config:
            model.add_constraint(
                model.get_variable(f"{var_name}_{self.name}_{time}") >= target - sum_var, constrainte_name
            )

    def _add_global_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Add global portfolio constraints."""
        # Power balance constraint
        residual_energy = self._compute_residual_energy(time, parameters)
        max_overall_imbal = max(residual_energy, parameters.maximum_imbalance)
        sum_power_variables = self._get_sum_power_level_variables(model, time)
        small_imbalance_up_var = model.get_variable(f"{self.name}_small_imbalance_up_{time}")
        large_imbalance_up_var = model.get_variable(f"{self.name}_large_imbalance_up_{time}")
        small_imbalance_down_var = model.get_variable(f"{self.name}_small_imbalance_down_{time}")
        large_imbalance_down_var = model.get_variable(f"{self.name}_large_imbalance_down_{time}")

        model.add_constraint(
            small_imbalance_up_var + large_imbalance_up_var - small_imbalance_down_var - large_imbalance_down_var
            == residual_energy - sum_power_variables,
            name=f"portfolio_balance_{time}",
        )

        # Imbalance limits
        model.add_constraint(
            (small_imbalance_up_var + large_imbalance_up_var <= max_overall_imbal),
            name=f"up_imbalance_limit_{time}",
        )

        model.add_constraint(
            (small_imbalance_down_var + large_imbalance_down_var <= max_overall_imbal),
            name=f"down_imbalance_limit_{time}",
        )

    def add_objective(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        if time in parameters.target_times:
            cfg.logger.debug(f"Adding objective terms for portfolio :{self.name} at time {time}")
            imbalance_prices = estimate_imbalance_prices(time, self.market_area, self.control_block, parameters)

            self._add_imbalance_cost_terms(
                model,
                time,
                *imbalance_prices,
                parameters.timestep,
            )

            self._add_reserve_penalty_terms(model, time, parameters)
        else:
            cfg.logger.debug(f"Skipping objective terms for portfolio :{self.name} at non-target time {time}")

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
        """Get imbalance cost terms as OR-Tools expressions."""

        small_imbalance_up_var = model.get_variable(f"{self.name}_small_imbalance_up_{time}")
        small_imbalance_down_var = model.get_variable(f"{self.name}_small_imbalance_down_{time}")
        large_imbalance_up_var = model.get_variable(f"{self.name}_large_imbalance_up_{time}")
        large_imbalance_down_var = model.get_variable(f"{self.name}_large_imbalance_down_{time}")

        # Small imbalance costs
        if imbalance_price_up:
            model.add_objective(
                imbalance_price_up * small_imbalance_up_var * timestep.total_hours(), direction="minimize"
            )

        if imbalance_price_down:
            model.add_objective(
                -imbalance_price_down * small_imbalance_down_var * timestep.total_hours(), direction="minimize"
            )

        # Large imbalance costs
        if large_imbalance_price_up:
            model.add_objective(
                large_imbalance_price_up * large_imbalance_up_var * timestep.total_hours(), direction="minimize"
            )

        if large_imbalance_price_down:
            model.add_objective(
                -large_imbalance_price_down * large_imbalance_down_var * timestep.total_hours(), direction="minimize"
            )

    def _add_reserve_penalty_terms(
        self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters
    ) -> None:
        """Get reserve penalty terms as OR-Tools expressions."""

        contracted_diff_up = model.get_variable(f"contracted_diff_up_{self.name}_{time}")
        contracted_diff_down = model.get_variable(f"contracted_diff_down_{self.name}_{time}")
        auto_contracted_diff_up = model.get_variable(f"automated_contracted_diff_up_{self.name}_{time}")
        auto_contracted_diff_down = model.get_variable(f"automated_contracted_diff_down_{self.name}_{time}")

        # Manual reserve penalties
        model.add_objective(
            parameters.manual_unprocured_reserves_penalty * parameters.timestep.total_hours() * contracted_diff_up,
            direction="minimize",
        )
        model.add_objective(
            parameters.manual_unprocured_reserves_penalty * parameters.timestep.total_hours() * contracted_diff_down,
            direction="minimize",
        )

        # Automated reserve penalties
        model.add_objective(
            parameters.automated_unprocured_reserves_penalty
            * parameters.timestep.total_hours()
            * auto_contracted_diff_up,
            direction="minimize",
        )
        model.add_objective(
            parameters.automated_unprocured_reserves_penalty
            * parameters.timestep.total_hours()
            * auto_contracted_diff_down,
            direction="minimize",
        )

    def _add_imbalance_variables(
        self,
        model: OptimisationModel,
        time: DateTime,
        residual_energy: float,
        maximum_power: float,
        parameters: PortfolioOptimisationParameters,
    ) -> None:
        """Add imbalance variables to the optimization model."""
        small_imbalance_limit = maximum_power * parameters.small_imbalance_size
        max_overall_imbal = max(residual_energy, parameters.maximum_imbalance)

        model.add_continuous_variable(
            name=f"{self.name}_small_imbalance_up_{time}",
            lower_bound=0,
            upper_bound=small_imbalance_limit,
        )
        model.add_continuous_variable(
            name=f"{self.name}_small_imbalance_down_{time}",
            lower_bound=0,
            upper_bound=small_imbalance_limit,
        )
        model.add_continuous_variable(
            name=f"{self.name}_large_imbalance_up_{time}",
            lower_bound=0,
            upper_bound=max_overall_imbal,
        )
        model.add_continuous_variable(
            name=f"{self.name}_large_imbalance_down_{time}",
            lower_bound=0,
            upper_bound=max_overall_imbal,
        )

    def _add_contract_difference_variables(
        self, model: OptimisationModel, time: DateTime, maximum_power: float
    ) -> None:
        """Add contract difference variables to the optimization model."""
        for v in [
            "contracted_diff_up",
            "contracted_diff_down",
            "automated_contracted_diff_up",
            "automated_contracted_diff_down",
        ]:
            model.add_continuous_variable(name=f"{v}_{self.name}_{time}", lower_bound=0, upper_bound=maximum_power)

    def _get_sum_power_level_variables(
        self,
        model: OptimisationModel,
        time: DateTime,
    ) -> float:
        """Get the sum of all power level variables for a specific time."""
        total_power = 0

        for storage in self.equipments.storage:
            if time in storage.optimisation_time_window:
                sell_var = model.get_variable(f"{storage.name}_power_level_sell_{time}")
                buy_var = model.get_variable(f"{storage.name}_power_level_buy_{time}")
                total_power += sell_var + buy_var

        for hydro in self.equipments.hydro:
            if time in hydro.optimisation_time_window:
                for category in hydro.fragment_data.keys():
                    var = model.get_variable(f"{hydro.name}_power_level_frag_{category}_{time}")
                    total_power += var

        for obj in (
            self.equipments.thermal
            + self.equipments.wind
            + self.equipments.solar
            + self.equipments.dispatchable_load
            + self.equipments.non_dispatchable_load
        ):
            if time in obj.optimisation_time_window:
                var = model.get_variable(f"{obj.name}_power_level_{time}")
                total_power += var

        return total_power

    def _compute_residual_energy(self, time: DateTime, parameters: PortfolioOptimisationParameters) -> float:
        """Compute residual energy metrics for all times."""
        residual_energy = 0.0

        forecast_based_equipment: list[LoadPO | OtherNonDispatchablePO] = [
            *self.equipments.non_dispatchable_load,
            *self.equipments.other_non_dispatchable,
            *self.equipments.dispatchable_load,
        ]

        for obj in forecast_based_equipment:
            upstream_energy = get_upstream_energy(obj, time, parameters)
            last_forecast = obj.maximum_power_forecast.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ).get_value(time)
            optimal_dispatch = min(last_forecast, upstream_energy)
            residual_energy += upstream_energy - optimal_dispatch

        # Other equipment types contribute their full upstream energy
        other_equipment = [
            *self.equipments.thermal,
            *self.equipments.storage,
            *self.equipments.hydro,
            *self.equipments.wind,
            *self.equipments.solar,
        ]

        for equipment in other_equipment:
            residual_energy += get_upstream_energy(equipment, time, parameters)  # type:ignore [arg-type]

        return residual_energy

    def _compute_maximum_power(self, time: DateTime, parameters: PortfolioOptimisationParameters) -> float:
        """Compute maximum power and energy metrics for all times."""
        return sum(
            abs(get_maximum_power(obj, time, parameters.execution_date))
            for _, equipment_list in self.equipments.get_dispatchable_equipment_types()
            for obj in equipment_list
        )

    def _compute_reserves_time(
        self, time: DateTime, parameters: PortfolioOptimisationParameters
    ) -> tuple[float, float, float, float]:
        """Compute reserves and power metrics for a specific time."""
        all_reserves = [
            get_reserve(obj, time, parameters)
            for _, equipment_list in self.equipments.get_dispatchable_equipment_types()
            for obj in equipment_list
        ]

        return tuple(sum(values) for values in zip(*all_reserves)) if all_reserves else (0.0, 0.0, 0.0, 0.0)  # noqa: B905

    def get_price_forecast(self, time: DateTime, parameters: PortfolioOptimisationParameters) -> float | None:
        """Get price forecast for given time based on market type and forecast settings."""

        if time in parameters.target_times:
            if parameters.use_forecast:
                if parameters.market == MarketType.dayahead:
                    return (
                        cast(ForecastingMatrix | LazyForecastingMatrix, self.market_area.price_forecast_medium)
                        .get_forecast(parameters.execution_date, time, time)
                        .get_value(time)
                    )
                elif parameters.market == MarketType.intraday:
                    return (
                        cast(ForecastingMatrix | LazyForecastingMatrix, self.market_area.id_price_forecast)
                        .get_forecast(parameters.execution_date, time, time)
                        .get_value(time)
                    )

            else:
                if parameters.market == MarketType.dayahead:
                    return cast(Timeseries | LazyTimeseries, self.market_area.da_price).get_value(time)
                elif parameters.market == MarketType.intraday:
                    return (
                        cast(ForecastingMatrix | LazyForecastingMatrix, self.market_area.id_price)
                        .get_forecast(parameters.execution_date, time, time)
                        .get_value(time)
                    )
                elif parameters.market == MarketType.rr_activation:
                    return cast(Timeseries | LazyTimeseries, self.market_area.rr_activation_price).get_value(time)
                elif parameters.market == MarketType.mfrr_activation:
                    return cast(Timeseries | LazyTimeseries, self.market_area.mfrr_activation_price).get_value(time)
        else:
            return self.market_area.price_forecast_medium.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )
        return None
