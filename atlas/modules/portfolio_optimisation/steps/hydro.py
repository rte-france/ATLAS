"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pendulum import DateTime

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.hydro import HydroDispatch
from atlas.common.optimal_dispatch.reserves import HydroReserveHandler, ReserveFactory
from atlas.common.optimal_dispatch.steps import AbstractOptimStep
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class HydroStep(AbstractOptimStep[HydroPO, "PortfolioOptimisationParameters"]):
    """
    LP step for a hydro reservoir unit. Composes :class:`HydroDispatch` (stored energy +
    fragments + balance) and :class:`HydroReserveHandler` (reserves + storage-level
    coupling). The PO-specific marginal-value pricing is kept here as it is a property of
    the objective, not the physical dispatch.
    """

    _reserves: HydroReserveHandler

    def __init__(self, equipment: HydroPO):
        super().__init__(equipment)
        self._dispatch = HydroDispatch(equipment)
        self._reserves = ReserveFactory.for_hydro(equipment, self._dispatch)

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        self._dispatch.setup(model, parameters)
        self._reserves.setup(model)
        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding variables for hydro unit {eq.name} at time {time}")
            self._dispatch.add_variables(time)
            self._reserves.add_variables(time, eq.maximum_power.get_value(time), eq.minimum_power.get_value(time))

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding constraints for hydro unit {eq.name} at time {time}")
            min_power = eq.minimum_power.get_value(time)
            max_power = eq.maximum_power.get_value(time)

            self._reserves.add_relaxed_reserve_constraint(time, min_power)
            self._reserves.add_automated_capacity_constraints(time)
            self._reserves.add_capacity_constraints(time, max_power)

            if time in parameters.target_times:
                self._dispatch.add_energy_balance(model, time, parameters)
                self._reserves.add_storage_level_constraints(
                    time, eq.minimum_energy.get_value(time), eq.maximum_energy.get_value(time)
                )

    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict | None = None
    ):
        if price_forecasts is None:
            price_forecasts = {}
        eq = self.equipment
        dt_h = parameters.temporal.timestep.total_hours()
        energy_level = self._get_current_energy_level(eq, parameters)
        marginal_weights = self._calculate_marginal_weights(eq, energy_level)

        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding objective for hydro unit {eq.name} at time {time}")
            price_forecast = price_forecasts.get(time, 0.0)

            for k in range(len(eq.fragment_data.keys())):
                fragment_price = self._calculate_fragment_price(eq.fragment_data[k].price, marginal_weights, time)
                power_level_frag_var = self._dispatch.get_fragment_var(time, k)

                if time in parameters.target_times:
                    model.add_objective(fragment_price * power_level_frag_var * dt_h)
                else:
                    model.add_objective(-(price_forecast - fragment_price) * power_level_frag_var * dt_h)

    @staticmethod
    def _get_current_energy_level(equipment: HydroPO, parameters: PortfolioOptimisationParameters) -> float:
        """Resolve the reservoir's energy level at the time just before optimisation starts."""
        prev = parameters.temporal.start_date - parameters.temporal.timestep
        if equipment._cached_energy_forecast and prev in equipment._cached_energy_forecast:
            return equipment._cached_energy_forecast.get_value(prev)
        return equipment.initial_level.get_value(prev)

    @staticmethod
    def _calculate_marginal_weights(equipment: HydroPO, energy_level: float) -> dict:
        """
        Compute interpolation weights between the two adjacent storage-marginal-value rows
        bracketing *energy_level*, used to price hydro fragments above/below the bracket.
        """
        storage_indices = equipment.storage_marginal_value.index

        x_min_candidates = [x for x in storage_indices if int(x) <= energy_level]
        x_max_candidates = [x for x in storage_indices if int(x) > energy_level]

        weights: dict = {
            "has_min": bool(x_min_candidates),
            "has_max": bool(x_max_candidates),
            "weight_inf": 0.0,
            "weight_sup": 0.0,
            "level_inf": None,
            "level_sup": None,
        }

        if x_min_candidates:
            xp_min = max(x_min_candidates, key=lambda x: int(x))
            weights["level_inf"] = equipment.storage_marginal_value.select(xp_min)

        if x_max_candidates:
            xp_max = min(x_max_candidates, key=lambda x: int(x))
            weights["level_sup"] = equipment.storage_marginal_value.select(xp_max)

        if weights["has_min"] and weights["has_max"]:
            range_diff = int(xp_max) - int(xp_min)
            weights["weight_inf"] = (int(xp_max) - energy_level) / range_diff
            weights["weight_sup"] = (energy_level - int(xp_min)) / range_diff

        return weights

    @staticmethod
    def _calculate_fragment_price(fragment_price: float, marginal_weights: dict, time: DateTime) -> float:
        """Apply the (interpolated) marginal-value adjustment to a base fragment price."""
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

        return fragment_price + marginal_adjustment
