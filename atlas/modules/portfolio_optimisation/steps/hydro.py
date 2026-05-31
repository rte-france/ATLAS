"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pendulum import DateTime

import atlas.config as cfg
from atlas.common.optimal_dispatch.steps import AbstractOptimStep
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class HydroStep(AbstractOptimStep[HydroPO]):
    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding variables for hydro unit {eq.name} at time {time}")
            min_power = eq.minimum_power.get_value(time)
            max_power = eq.maximum_power.get_value(time)
            max_energy = eq.maximum_energy.get_value(time)
            maximum_automated = get_maximum_automated(eq)

            model.add_continuous_variable(name=f"{eq.name}_stored_energy_{time}", lower_bound=0, upper_bound=max_energy)

            for category, fragment in eq.fragment_data.items():
                volume = eq.maximum_power.get_value(time) * fragment.volume
                model.add_continuous_variable(
                    name=f"{eq.name}_power_level_frag_{category}_{time}", lower_bound=0, upper_bound=volume
                )

            add_reserve_variables(
                model,
                eq.name,
                time,
                min_power,
                max_power,
                maximum_automated,
                relaxed_reserves=True,
                storage_equipment=False,
                thermal_equipment=False,
            )

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding constraints for hydro unit {eq.name} at time {time}")

            maximum_energy = eq.maximum_energy.get_value(time)
            minimum_energy = eq.minimum_energy.get_value(time)
            min_power = eq.minimum_power.get_value(time)
            max_power = eq.maximum_power.get_value(time)

            automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{eq.name}_{time}")
            automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{eq.name}_{time}")
            relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{eq.name}_{time}")
            reserves_up_var = model.get_variable(f"reserves_up_{eq.name}_{time}")
            reserves_down_var = model.get_variable(f"reserves_down_{eq.name}_{time}")
            stored_energy_var = model.get_variable(f"{eq.name}_stored_energy_{time}")

            model.add_constraint(relaxed_reserves_var <= min_power, f"relaxed_reserves_{time}_{eq.name}")
            model.add_constraint(
                automated_reserves_up_var <= get_maximum_automated(eq), f"automated_reserves_up_max_{time}_{eq.name}"
            )
            model.add_constraint(
                automated_reserves_down_var <= get_maximum_automated(eq),
                f"automated_reserves_down_max_{time}_{eq.name}",
            )
            model.add_constraint(reserves_up_var <= max_power, f"reserves_up_max_{time}_{eq.name}")
            model.add_constraint(reserves_down_var <= max_power, f"reserves_down_max_{time}_{eq.name}")

            power_level_fragment_sum_var = sum(
                model.get_variable(f"{eq.name}_power_level_frag_{category}_{time}") for category in eq.fragment_data
            )

            if time in parameters.target_times:
                inflow = (
                    eq.inflows.get_value(time) * parameters.temporal.timestep.total_days()
                    if eq.inflows is not None
                    else 0
                )

                if time == parameters.temporal.start_date:
                    model.add_constraint(
                        stored_energy_var
                        == eq.initial_level.get_value(parameters.temporal.start_date - parameters.temporal.timestep)
                        - power_level_fragment_sum_var * parameters.temporal.timestep.total_hours()
                        + inflow,
                        f"storage_level_evol_{time}_{eq.name}",
                    )
                else:
                    stored_energy_prev_var = model.get_variable(
                        f"{eq.name}_stored_energy_{time - parameters.temporal.timestep}"
                    )
                    model.add_constraint(
                        stored_energy_var
                        == stored_energy_prev_var
                        - power_level_fragment_sum_var * parameters.temporal.timestep.total_hours()
                        + inflow,
                        f"storage_level_evol_{time}_{eq.name}",
                    )

                reserve_stored_energy_up_var = reserves_up_var + automated_reserves_up_var
                reserve_stored_energy_down_var = reserves_down_var + automated_reserves_down_var

                model.add_constraint(
                    stored_energy_var >= minimum_energy + reserve_stored_energy_up_var,
                    f"min_storage_level_{time}_{eq.name}",
                )
                model.add_constraint(
                    stored_energy_var <= maximum_energy - reserve_stored_energy_down_var,
                    f"max_storage_level_{time}_{eq.name}",
                )

    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict | None = None
    ):
        if price_forecasts is None:
            price_forecasts = {}
        eq = self.equipment
        energy_level = self._get_current_energy_level(eq, parameters)
        marginal_weights = self._calculate_marginal_weights(eq, energy_level)

        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding objective for hydro unit {eq.name} at time {time}")
            price_forecast = price_forecasts.get(time, 0.0)

            for k in range(len(eq.fragment_data.keys())):
                fragment_price = self._calculate_fragment_price(eq.fragment_data[k].price, marginal_weights, time)
                power_level_frag_var = model.get_variable(f"{eq.name}_power_level_frag_{k}_{time}")

                if time in parameters.target_times:
                    model.add_objective(
                        fragment_price * power_level_frag_var * parameters.temporal.timestep.total_hours()
                    )
                else:
                    model.add_objective(
                        -(price_forecast - fragment_price)
                        * power_level_frag_var
                        * parameters.temporal.timestep.total_hours()
                    )
            cfg.logger.debug(f"Finished adding objective for hydro unit {eq.name} at time {time}")

    @staticmethod
    def _get_current_energy_level(equipment: HydroPO, parameters: PortfolioOptimisationParameters) -> float:
        """
        Get the current energy level from forecast or initial level.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Current energy level
        :rtype: float
        """
        if (
            equipment._cached_energy_forecast
            and parameters.temporal.start_date - parameters.temporal.timestep in equipment._cached_energy_forecast
        ):
            return equipment._cached_energy_forecast.get_value(
                parameters.temporal.start_date - parameters.temporal.timestep
            )
        else:
            return equipment.initial_level.get_value(parameters.temporal.start_date - parameters.temporal.timestep)

    @staticmethod
    def _calculate_marginal_weights(equipment: HydroPO, energy_level: float) -> dict:
        """
        Calculate marginal value weights based on current energy level.

        :param energy_level: Current energy level
        :type energy_level: float
        :return: Dictionary containing marginal weights and related data
        :rtype: dict
        """
        storage_indices = equipment.storage_marginal_value.index

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
            weights["level_inf"] = equipment.storage_marginal_value.select(xp_min)  # type: ignore[assignment]

        if x_max_candidates:
            xp_max = min(x_max_candidates, key=lambda x: int(x))
            weights["level_sup"] = equipment.storage_marginal_value.select(xp_max)  # type: ignore[assignment]

        if weights["has_min"] and weights["has_max"]:
            range_diff = int(xp_max) - int(xp_min)
            weights["weight_inf"] = (int(xp_max) - energy_level) / range_diff
            weights["weight_sup"] = (energy_level - int(xp_min)) / range_diff

        return weights

    @staticmethod
    def _calculate_fragment_price(fragment_price: float, marginal_weights: dict, time: DateTime) -> float:
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

        if not marginal_weights["has_min"] and marginal_weights["has_max"]:
            marginal_adjustment = cast(AbstractTimeseries, marginal_weights["level_sup"]).get_value(time)
        elif marginal_weights["has_min"] and not marginal_weights["has_max"]:
            marginal_adjustment = cast(AbstractTimeseries, marginal_weights["level_inf"]).get_value(time)
        elif marginal_weights["has_min"] and marginal_weights["has_max"]:
            p_min = cast(AbstractTimeseries, marginal_weights["level_inf"]).get_value(time)
            p_max = cast(AbstractTimeseries, marginal_weights["level_sup"]).get_value(time)
            marginal_adjustment = marginal_weights["weight_inf"] * p_min + marginal_weights["weight_sup"] * p_max
        else:
            marginal_adjustment = 0.0

        return base_price + marginal_adjustment
