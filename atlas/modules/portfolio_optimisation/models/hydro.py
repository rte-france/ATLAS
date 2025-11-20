"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import cast

from pendulum import DateTime, Duration

import atlas.config as cfg
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.hydro import Hydro
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes


class HydroPO(Hydro):
    maximum_energy: Timeseries | LazyTimeseries
    minimum_energy: Timeseries | LazyTimeseries
    maximum_fcr: float
    maximum_afrr: float
    minimum_power: Timeseries | LazyTimeseries
    maximum_power: Timeseries | LazyTimeseries
    initial_level: Timeseries | LazyTimeseries
    storage_marginal_value: ScenarioMatrix | LazyScenarioMatrix

    optimisation_time_window: list[DateTime] = []

    def add_variables(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        """Build variables for hydro equipment."""
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
        """Formulates hydraulic reservoir offers by calculating fragment prices and volumes."""

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
            if time == parameters.start_date:
                inflow = self.inflows.get_value(time) if self.inflows is not None else 0
                model.add_constraint(
                    stored_energy_var
                    == self.get_initial_level(parameters).get_value(parameters.start_date - parameters.timestep)
                    - power_level_fragment_sum_var * parameters.timestep.total_hours()
                    + inflow / parameters.timestep.total_days(),
                    f"storage_level_evol_{time}_{self.name}",
                )

            else:
                stored_energy_prev_var = model.get_variable(f"{self.name}_stored_energy_{time - parameters.timestep}")

                inflow = self.inflows.get_value(time) if self.inflows is not None else 0
                model.add_constraint(
                    stored_energy_var
                    == stored_energy_prev_var
                    - power_level_fragment_sum_var * parameters.timestep.total_hours()
                    + inflow / parameters.timestep.total_days(),
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
            for k in range(len(self.fragment_data.keys())):
                fragment_price = self.compute_fragment_prices(time, k, parameters)

                power_level_frag_var = model.get_variable(f"{self.name}_power_level_frag_{k}_{time}")

                if time in parameters.target_times:
                    model.add_objective(
                        fragment_price * power_level_frag_var * parameters.timestep.total_hours(),
                        direction="minimize",
                    )

                else:
                    model.add_objective(
                        -(price_forecast - fragment_price) * power_level_frag_var * parameters.timestep.total_hours(),
                        direction="minimize",
                    )
            cfg.logger.debug(f"Finished adding objective for hydro unit {self.name} at time {time}")
        else:
            cfg.logger.debug(
                f"Skipping objective for hydro unit {self.name} at time {time} - not in optimization times or target times"
            )

    def compute_fragment_prices(
        self,
        time: DateTime,
        category,
        parameters: PortfolioOptimisationParameters,
    ) -> float:
        energy_level = self._get_current_energy_level(parameters)

        marginal_weights = self._calculate_marginal_weights(energy_level, parameters.timestep)

        return self._calculate_fragment_price(self.fragment_data[category].price, marginal_weights, time)

    def _get_current_energy_level(self: HydroPO, parameters: PortfolioOptimisationParameters) -> float:
        """Get the current energy level from forecast or initial level."""
        if self.stored_energy:
            energy_forecast = self.stored_energy.get_forecast(
                parameters.execution_date,
                parameters.start_date - parameters.timestep,
                parameters.start_date - parameters.timestep,
            )

            return energy_forecast.get_value(parameters.start_date - parameters.timestep)
        else:
            return self.initial_level.get_value(parameters.start_date - parameters.timestep)

    def _calculate_marginal_weights(self, energy_level: float, timestep: Duration) -> dict:  # noqa: ARG002
        """Calculate marginal value weights based on current energy level."""
        storage_indices = self.storage_marginal_value.indexes

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
        """Calculate the final fragment price including marginal values."""
        base_price = fragment_price

        # Apply marginal value adjustments based on available bounds
        if not marginal_weights["has_min"] and marginal_weights["has_max"]:
            # Only upper bound available
            marginal_adjustment = cast(Timeseries | LazyTimeseries, marginal_weights["level_sup"]).get_value(time)
        elif marginal_weights["has_min"] and not marginal_weights["has_max"]:
            # Only lower bound available
            marginal_adjustment = cast(Timeseries | LazyTimeseries, marginal_weights["level_inf"]).get_value(time)
        elif marginal_weights["has_min"] and marginal_weights["has_max"]:
            # Both bounds available - interpolate
            p_min = cast(Timeseries | LazyTimeseries, marginal_weights["level_inf"]).get_value(time)
            p_max = cast(Timeseries | LazyTimeseries, marginal_weights["level_sup"]).get_value(time)
            marginal_adjustment = marginal_weights["weight_inf"] * p_min + marginal_weights["weight_sup"] * p_max
        else:
            # No bounds available
            marginal_adjustment = 0.0

        return base_price + marginal_adjustment

    def get_initial_level(self: HydroPO, parameters: PortfolioOptimisationParameters) -> Timeseries:
        if self.stored_energy:
            if (
                self.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.start_date - parameters.timestep,
                    parameters.end_date,
                ).first_date()
                < parameters.start_date
            ):
                return self.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.start_date - parameters.timestep,
                    parameters.end_date,
                )

            else:
                return (
                    self.initial_level.slice(
                        start_bound=parameters.start_date - parameters.timestep,
                        end_bound=parameters.end_date,
                    )
                    if isinstance(self.initial_level, Timeseries)
                    else self.initial_level.slice(
                        start_bound=parameters.start_date - parameters.timestep,
                        end_bound=parameters.end_date,
                    ).collect()
                )

        else:
            return (
                self.initial_level.slice(
                    start_bound=parameters.start_date - parameters.timestep,
                    end_bound=parameters.end_date,
                )
                if isinstance(self.initial_level, Timeseries)
                else self.initial_level.slice(
                    start_bound=parameters.start_date - parameters.timestep,
                    end_bound=parameters.end_date,
                ).collect()
            )

    def get_optimisation_time_window(
        self, start_date: DateTime, end_date: DateTime, timestep: Duration
    ) -> list[DateTime]:
        """Get optimisation time windows based on additional hours."""

        self.optimisation_time_window = generate_datetimes(
            start=start_date, end=end_date + self.additional_hours, freq=timestep
        )
        return self.optimisation_time_window
