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
from atlas.modules.portfolio_optimisation.models import EquipmentPO
from atlas.modules.portfolio_optimisation.models.control_block import ControlBlockPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.market_area import MarketAreaPO
from atlas.modules.portfolio_optimisation.models.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_power, get_reserve, get_upstream_energy
from atlas.modules.portfolio_optimisation.utils.imbalance_price import estimate_imbalance_prices
from atlas.solver.solver_interface import OptimisationModel


class PortfolioPO(Portfolio):
    market_area: MarketAreaPO
    control_block: ControlBlockPO
    equipments: dict[str, list[EquipmentPO]]

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
            if any(self.equipments.get(tech, []) for tech in ["thermal", "storage", "wind", "solar", "hydro"]):
                self._add_reserves_constraints(time, model, parameters)
        else:
            cfg.logger.debug(f"Skipping constraints for portfolio :{self.name} at non-target time {time}")

    def _add_reserves_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        reserve_equipment_types = ["storage", "wind", "solar", "hydro", "thermal"]

        sum_reserves_up_var = sum(
            model.get_variable(f"reserves_up_{obj.name}_{time}")
            for t in reserve_equipment_types
            if t in self.equipments
            for obj in self.equipments[t]
        )
        sum_reserves_down_var = sum(
            model.get_variable(f"reserves_down_{obj.name}_{time}")
            for t in reserve_equipment_types
            if t in self.equipments
            for obj in self.equipments[t]
        )
        sum_automated_reserves_up_var = sum(
            model.get_variable(f"automated_reserves_up_{obj.name}_{time}")
            for t in reserve_equipment_types
            if t in self.equipments
            for obj in self.equipments[t]
        )
        sum_automated_reserves_down_var = sum(
            model.get_variable(f"automated_reserves_down_{obj.name}_{time}")
            for t in reserve_equipment_types
            if t in self.equipments
            for obj in self.equipments[t]
        )

        (
            reserves_up,
            reserves_down,
            automated_reserves_up,
            automated_reserves_down,
        ) = self._compute_reserves_time(time, parameters)

        model.add_constraint(
            model.get_variable(f"contracted_diff_up_{self.name}_{time}") >= reserves_up - sum_reserves_up_var
        )

        model.add_constraint(
            model.get_variable(f"contracted_diff_down_{self.name}_{time}") >= reserves_down - sum_reserves_down_var
        )

        model.add_constraint(
            model.get_variable(f"automated_contracted_diff_up_{self.name}_{time}")
            >= automated_reserves_up - sum_automated_reserves_up_var
        )

        model.add_constraint(
            model.get_variable(f"automated_contracted_diff_down_{self.name}_{time}")
            >= automated_reserves_down - sum_automated_reserves_down_var
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

        power_balance_constraint = (
            small_imbalance_up_var + large_imbalance_up_var - small_imbalance_down_var - large_imbalance_down_var
            == residual_energy - sum_power_variables
        )
        model.add_constraint(power_balance_constraint, name=f"power_balance_{time}")

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
    ):
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
    ):
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
    ):
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
        self,
        model: OptimisationModel,
        time: DateTime,
        maximum_power: float,
    ):
        """Add contract difference variables to the optimization model."""
        contract_vars = [
            "contracted_diff_up",
            "contracted_diff_down",
            "automated_contracted_diff_up",
            "automated_contracted_diff_down",
        ]

        for var_type in contract_vars:
            model.add_continuous_variable(
                name=f"{var_type}_{self.name}_{time}",
                lower_bound=0,
                upper_bound=maximum_power,
            )

    def _get_sum_power_level_variables(
        self,
        model: OptimisationModel,
        time: DateTime,
    ) -> float:
        """Get the sum of all power level variables for a specific time."""
        total_power = 0

        for object_type in self.equipments.keys():
            for obj in self.equipments[object_type]:
                if time in obj.optimisation_time_window:
                    if object_type == "storage":
                        sell_var = model.get_variable(f"{obj.name}_power_level_sell_{time}")
                        buy_var = model.get_variable(f"{obj.name}_power_level_buy_{time}")
                        total_power += sell_var + buy_var

                    elif object_type == "hydro":
                        for category in obj.fragment_data.keys():
                            var = model.get_variable(f"{obj.name}_power_level_frag_{category}_{time}")
                            total_power += var
                    elif object_type == "other_non_dispatchable":
                        continue
                    else:
                        var = model.get_variable(f"{obj.name}_power_level_{time}")
                        total_power += var

        return total_power

    def _compute_residual_energy(self, time: DateTime, parameters: PortfolioOptimisationParameters) -> float:
        """Compute residual energy metrics for all times."""

        return (
            self._compute_non_dispatchable_production_residual_energy(time, parameters)
            + self._compute_non_dispatchable_load_residual_energy(time, parameters)
            + self._compute_dispatchable_residual_energy(time, parameters)
        )

    def _compute_maximum_power(
        self,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> float:
        """Compute maximum power and energy metrics for all times."""
        sum_maximum_power: float = 0

        for equipment_type in ["dispatchable_load", "wind", "solar", "hydro", "storage", "thermal"]:
            for obj in self.equipments.get(equipment_type, []):
                sum_maximum_power += abs(get_maximum_power(obj, time, parameters.execution_date))

        return sum_maximum_power

    def _compute_dispatchable_residual_energy(
        self, time: DateTime, parameters: PortfolioOptimisationParameters
    ) -> float:
        """Compute residual energy for dispatchable equipment."""
        residual_energy: float = 0

        for equipment_type in self.equipments.keys():
            for obj in self.equipments.get(equipment_type, []):
                upstream_energy = get_upstream_energy(obj, time, parameters)
                if equipment_type in ["non_dispatchable_load", "other_non_dispatchable", "dispatchable_load"]:
                    last_forecast = obj.maximum_power_forecast.get_forecast(
                        parameters.execution_date, parameters.start_date, parameters.end_date
                    ).get_value(time)
                    optimal_dispatch = min(last_forecast, upstream_energy)
                    residual_energy += upstream_energy - optimal_dispatch
                else:
                    residual_energy += upstream_energy

        return residual_energy

    def _compute_non_dispatchable_production_residual_energy(
        self,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> float:
        """Compute non-dispatchable production equipment residual energy"""
        residual_energy = 0.0

        for obj in cast(list[OtherNonDispatchablePO], self.equipments.get("other_non_dispatchable", [])):
            last_forecast_ti = obj.maximum_power_forecast.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ).get_value(time)

            upstream_sold_energy = get_upstream_energy(obj, time, parameters)
            optimal_dispatch = min(last_forecast_ti, upstream_sold_energy)
            residual_energy += upstream_sold_energy - optimal_dispatch

        return residual_energy

    def _compute_non_dispatchable_load_residual_energy(
        self,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> float:
        """Compute non-dispatchable load equipment residual energy"""
        residual_energy = 0.0

        for obj in cast(list[LoadPO], self.equipments.get("non_dispatchable_load", [])):
            last_forecast_ti = obj.maximum_power_forecast.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ).get_value(time)

            upstream_bought_energy = get_upstream_energy(obj, time, parameters)
            optimal_dispatch = min(last_forecast_ti, upstream_bought_energy)
            residual_energy += upstream_bought_energy - optimal_dispatch

        return residual_energy

    def _compute_reserves_time(
        self, time: DateTime, parameters: PortfolioOptimisationParameters
    ) -> tuple[float, float, float, float]:
        """Compute reserves and power metrics for a specific time."""
        sum_reserves_up: float = 0
        sum_reserves_down: float = 0
        sum_automated_reserves_up: float = 0
        sum_automated_reserves_down: float = 0

        equipment_types = ["dispatchable_load", "wind", "solar", "hydro", "storage", "thermal"]

        for equipment_type in equipment_types:
            for obj in self.equipments.get(equipment_type, []):
                (
                    reserves_up,
                    reserves_down,
                    automated_reserves_up,
                    automated_reserves_down,
                ) = get_reserve(obj, time, parameters)

                sum_reserves_up += reserves_up
                sum_reserves_down += reserves_down
                sum_automated_reserves_up += automated_reserves_up
                sum_automated_reserves_down += automated_reserves_down

        return (
            sum_reserves_up,
            sum_reserves_down,
            sum_automated_reserves_up,
            sum_automated_reserves_down,
        )

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
