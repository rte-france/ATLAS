"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import cast

from pendulum import DateTime, Duration

import atlas.config as cfg
from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.hydro import Hydro
from atlas.modules.portfolio_optimisation.models.base_equipment import BaseEquipmentPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel


class HydroPO(BaseEquipmentPO, Hydro):
    maximum_energy: AbstractTimeseries
    minimum_energy: AbstractTimeseries
    maximum_fcr: float
    maximum_afrr: float
    minimum_power: AbstractTimeseries
    maximum_power: AbstractTimeseries
    initial_level: AbstractTimeseries
    storage_marginal_value: AbstractScenarioMatrix
    additional_hours: Duration

    optimisation_time_window: list[DateTime] = []
    _cached_energy_forecast: Timeseries | None = None

    def add_variables(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        """
        Build variables for hydro equipment.

        :param model: Optimization model
        :type model: OptimisationModel
        :param time: Current time period
        :type time: DateTime
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        """
        if time in self.optimisation_time_window:
            cfg.logger.debug(f"Adding variables for hydro unit {self.name} at time {time}")
            min_power = self.minimum_power.get_value(time)
            max_power = self.maximum_power.get_value(time)
            max_energy = self.maximum_energy.get_value(time)
            maximum_automated = get_maximum_automated(self)

            model.add_continuous_variable(
                name=f"{self.name}_stored_energy_{time}",
                lower_bound=0,
                upper_bound=max_energy,
            )

            self.add_variable_fragment(model=model, time=time)

            add_reserve_variables(
                model,
                self.name,
                time,
                min_power,
                max_power,
                maximum_automated,
                relaxed_reserves=True,
                storage_equipment=False,
                thermal_equipment=False,
            )
        else:
            cfg.logger.debug(f"Skipping variables for hydro unit {self.name} at non-hydraulic-op time {time}")

    def add_variable_fragment(
        self,
        model: OptimisationModel,
        time: DateTime,
    ):
        """
        Formulates hydraulic reservoir offers by calculating fragment prices and volumes.

        :param model: Optimization model
        :type model: OptimisationModel
        :param time: Current time period
        :type time: DateTime
        """

        for category, fragment in self.fragment_data.items():
            volume = self.maximum_power.get_value(time) * fragment.volume

            model.add_continuous_variable(
                name=f"{self.name}_power_level_frag_{category}_{time}",
                lower_bound=0,
                upper_bound=volume,
            )

    def add_constraints(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        This function formulates the hydraulic reservoir offers.
        """
        if time in self.optimisation_time_window:
            cfg.logger.debug(f"Adding constraints for hydro unit {self.name} at time {time}")

            maximum_energy = self.maximum_energy.get_value(time)
            minimum_energy = self.minimum_energy.get_value(time)
            min_power = self.minimum_power.get_value(time)
            max_power = self.maximum_power.get_value(time)

            automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.name}_{time}")
            automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.name}_{time}")
            relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.name}_{time}")
            reserves_up_var = model.get_variable(f"reserves_up_{self.name}_{time}")
            reserves_down_var = model.get_variable(f"reserves_down_{self.name}_{time}")
            stored_energy_var = model.get_variable(f"{self.name}_stored_energy_{time}")

            model.add_constraint(relaxed_reserves_var <= min_power, f"relaxed_reserves_{time}_{self.name}")
            model.add_constraint(
                automated_reserves_up_var <= get_maximum_automated(self),
                f"automated_reserves_up_max_{time}_{self.name}",
            )
            model.add_constraint(
                automated_reserves_down_var <= get_maximum_automated(self),
                f"automated_reserves_down_max_{time}_{self.name}",
            )
            model.add_constraint(reserves_up_var <= max_power, f"reserves_up_max_{time}_{self.name}")
            model.add_constraint(reserves_down_var <= max_power, f"reserves_down_max_{time}_{self.name}")

            power_level_fragment_sum_var = sum(
                model.get_variable(f"{self.name}_power_level_frag_{category}_{time}") for category in self.fragment_data
            )

        if time in parameters.target_times:
            # Default to 0 if inflows data is not provided (e.g., reservoir without natural inflows)
            inflow = (
                self.inflows.get_value(time) * parameters.temporal.timestep.total_days() if self.inflows is not None else 0
            )

            if time == parameters.temporal.start_date:
                model.add_constraint(
                    stored_energy_var
                    == self.initial_level.get_value(parameters.temporal.start_date - parameters.temporal.timestep)
                    - power_level_fragment_sum_var * parameters.temporal.timestep.total_hours()
                    + inflow,
                    f"storage_level_evol_{time}_{self.name}",
                )

            else:
                stored_energy_prev_var = model.get_variable(
                    f"{self.name}_stored_energy_{time - parameters.temporal.timestep}"
                )

                model.add_constraint(
                    stored_energy_var
                    == stored_energy_prev_var
                    - power_level_fragment_sum_var * parameters.temporal.timestep.total_hours()
                    + inflow,
                    f"storage_level_evol_{time}_{self.name}",
                )

            reserve_stored_energy_up_var = reserves_up_var + automated_reserves_up_var
            reserve_stored_energy_down_var = reserves_down_var + automated_reserves_down_var

            model.add_constraint(
                stored_energy_var >= minimum_energy + reserve_stored_energy_up_var,
                f"min_storage_level_{time}_{self.name}",
            )
            model.add_constraint(
                stored_energy_var <= maximum_energy - reserve_stored_energy_down_var,
                f"max_storage_level_{time}_{self.name}",
            )
        else:
            cfg.logger.debug(f"Skipping constraints for hydro unit {self.name} at non-hydraulic-op time {time}")

    def add_objective(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
        price_forecast: float = 0.0,
        **kwargs,
    ):
        if time in self.optimisation_time_window:
            cfg.logger.debug(f"Adding objective for hydro unit {self.name} at time {time}")

            energy_level = self._get_current_energy_level(parameters)
            marginal_weights = self._calculate_marginal_weights(energy_level)

            for k in range(len(self.fragment_data.keys())):
                fragment_price = self._calculate_fragment_price(self.fragment_data[k].price, marginal_weights, time)

                power_level_frag_var = model.get_variable(f"{self.name}_power_level_frag_{k}_{time}")

                if time in parameters.target_times:
                    model.add_objective(
                        fragment_price * power_level_frag_var * parameters.temporal.timestep.total_hours(),
                    )

                else:
                    model.add_objective(
                        -(price_forecast - fragment_price)
                        * power_level_frag_var
                        * parameters.temporal.timestep.total_hours(),
                    )
            cfg.logger.debug(f"Finished adding objective for hydro unit {self.name} at time {time}")
        else:
            cfg.logger.debug(
                f"Skipping objective for hydro unit {self.name} at time {time} - not in optimization times or target times"
            )

    def _get_current_energy_level(self: HydroPO, parameters: PortfolioOptimisationParameters) -> float:
        """
        Get the current energy level from forecast or initial level.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Current energy level
        :rtype: float
        """
        if (
            self._cached_energy_forecast
            and parameters.temporal.start_date - parameters.temporal.timestep in self._cached_energy_forecast
        ):
            return self._cached_energy_forecast.get_value(parameters.temporal.start_date - parameters.temporal.timestep)
        else:
            return self.initial_level.get_value(parameters.temporal.start_date - parameters.temporal.timestep)

    def _calculate_marginal_weights(self, energy_level: float) -> dict:
        """
        Calculate marginal value weights based on current energy level.

        :param energy_level: Current energy level
        :type energy_level: float
        :return: Dictionary containing marginal weights and related data
        :rtype: dict
        """
        storage_indices = self.storage_marginal_value.index

        x_min_candidates = [x for x in storage_indices if int(x) <= energy_level]
        x_max_candidates = [x for x in storage_indices if int(x) > energy_level]

        weights = {
            "has_min": bool(x_min_candidates),
            "has_max": bool(x_max_candidates),
            "weight_inf": 0.0,
            "weight_sup": 0.0,
            "level_inf": None,
            "level_sup": None,
        }

        if x_min_candidates:
            xp_min = max(x_min_candidates, key=lambda x: int(x))
            weights["level_inf"] = self.storage_marginal_value.select(xp_min)  # type: ignore[assignment]

        if x_max_candidates:
            xp_max = min(x_max_candidates, key=lambda x: int(x))
            weights["level_sup"] = self.storage_marginal_value.select(xp_max)  # type: ignore[assignment]

        # Calculate interpolation weights if we have both bounds
        if weights["has_min"] and weights["has_max"]:
            range_diff = int(xp_max) - int(xp_min)
            weights["weight_inf"] = (int(xp_max) - energy_level) / range_diff
            weights["weight_sup"] = (energy_level - int(xp_min)) / range_diff

        return weights

    def _calculate_fragment_price(self, fragment_price: float, marginal_weights: dict, time: DateTime) -> float:
        """
        Calculate the final fragment price including marginal values.

        :param fragment_price: Base fragment price
        :type fragment_price: float
        :param marginal_weights: Marginal weights dictionary
        :type marginal_weights: dict
        :param time: Current time period
        :type time: DateTime
        :return: Final fragment price
        :rtype: float
        """
        base_price = fragment_price

        # Apply marginal value adjustments based on available bounds
        if not marginal_weights["has_min"] and marginal_weights["has_max"]:
            # Only upper bound available
            marginal_adjustment = cast(AbstractTimeseries, marginal_weights["level_sup"]).get_value(time)
        elif marginal_weights["has_min"] and not marginal_weights["has_max"]:
            # Only lower bound available
            marginal_adjustment = cast(AbstractTimeseries, marginal_weights["level_inf"]).get_value(time)
        elif marginal_weights["has_min"] and marginal_weights["has_max"]:
            # Both bounds available - interpolate
            p_min = cast(AbstractTimeseries, marginal_weights["level_inf"]).get_value(time)
            p_max = cast(AbstractTimeseries, marginal_weights["level_sup"]).get_value(time)
            marginal_adjustment = marginal_weights["weight_inf"] * p_min + marginal_weights["weight_sup"] * p_max
        else:
            # No bounds available
            marginal_adjustment = 0.0

        return base_price + marginal_adjustment

    def prefetch_forecasts(self, execution_date: DateTime, timestep: Duration, start_date: DateTime):
        """
        Pre-fetch and cache forecasts for the entire optimization time window.

        :param execution_date: Execution date for forecasts
        :type execution_date: DateTime
        :param timestep: Time step duration
        :type timestep: Duration
        :param start_date: Start date for optimization
        :type start_date: DateTime
        """
        if self.stored_energy:
            # For hydro, we need the energy level at start_date - timestep
            initial_time = start_date - timestep
            self._cached_energy_forecast = self.stored_energy.get_forecast(execution_date, initial_time, initial_time)
