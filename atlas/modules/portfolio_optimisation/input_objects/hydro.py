"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import cast

from pendulum import DateTime, Duration

from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.objects.equipment.hydro import Hydro


class HydroPO(Hydro):
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
            initial_time = start_date - timestep
            self._cached_energy_forecast = self.stored_energy.get_forecast(execution_date, initial_time, initial_time)
