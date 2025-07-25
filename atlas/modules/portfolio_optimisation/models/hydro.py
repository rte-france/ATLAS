"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime
from pydantic import BaseModel

import atlas.config as cfg
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.hydro import Hydro
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel


class HydroPO(Hydro):
    maximum_energy: Timeseries | LazyTimeseries
    minimum_energy: Timeseries | LazyTimeseries
    maximum_fcr: float
    maximum_afrr: float
    minimum_power: Timeseries | LazyTimeseries
    maximum_power: Timeseries | LazyTimeseries
    stored_energy: ForecastingMatrix | LazyForecastingMatrix
    initial_level: Timeseries | LazyTimeseries
    storage_marginal_value: ScenarioMatrix | LazyScenarioMatrix

    def add_variables(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        """Build variables for hydro equipment."""
        cfg.logger.debug(f"Adding variables for hydro unit {self.name} at time {time}")
        if time in parameters.hydraulic_op_times:
            min_power = self.minimum_power.get_value(time)
            max_power = self.maximum_power.get_value(time)
            max_energy = self.maximum_energy.get_value(time)
            maximum_automated = get_maximum_automated(self)

            model.add_continuous_variable(
                name=f"{self.name}_stored_energy_{time}",
                lower_bound=0,
                upper_bound=max_energy,
            )

            self.add_variable_fragment(model=model, time=time, parameters=parameters)

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

    def add_variable_fragment(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ):
        """Formulates hydraulic reservoir offers by calculating fragment prices and volumes."""

        fragment_data = self._get_fragment_data()

        if time in parameters.hydraulic_op_times:
            for category, fragment in fragment_data.items():
                volume = self.maximum_power.get_value(time) * fragment.volume

                model.add_continuous_variable(
                    name=f"{self.name}_power_level_frag_{category}_at_{time}",
                    lower_bound=0,
                    upper_bound=volume,
                )

    def add_constraints(
        self,
        time: DateTime,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        This function formulates the hydraulic reservoir offers.
        """
        if time in parameters.hydraulic_op_times:
            max_power = self.maximum_power.get_value(time)
            maximum_energy = self.maximum_energy.get_value(time)
            minimum_energy = self.minimum_energy.get_value(time)
            min_power = self.minimum_power.get_value(time)

            model.add_constraint(model.get_variable(f"relaxed_reserves_{self.name}_{time}") <= min_power)
            model.add_constraint(
                model.get_variable(f"automated_reserves_up_{self.name}_{time}") <= get_maximum_automated(self)
            )
            model.add_constraint(
                model.get_variable(f"automated_reserves_up_{self.name}_{time}") <= get_maximum_automated(self)
            )
            model.add_constraint(model.get_variable(f"reserves_up_{self.name}_{time}") <= max_power)
            model.add_constraint(model.get_variable(f"reserves_up_{self.name}_{time}") <= max_power)

            stored_energy_var = model.get_variable(f"{self.name}_stored_energy_{time}")
            previous_stored_energy_var = model.get_variable(f"{self.name}_stored_energy_{time - parameters.timestep}")

            power_level_fragment_sum_var = sum(
                model.get_variable(f"{self.name}_power_level_frag_{category}_at_{time}")
                for category in self._get_fragment_data()
            )

            if time == parameters.start_date:
                model.add_constraint(
                    stored_energy_var
                    == self.get_initial_level(parameters).get_value(parameters.start_date - parameters.timestep)
                    - power_level_fragment_sum_var * parameters.timestep
                )

            elif time in parameters.target_times:
                model.add_constraint(
                    stored_energy_var == previous_stored_energy_var - power_level_fragment_sum_var * parameters.timestep
                )

            # For any time steps:
            # Respect of minimum and maximum stock constraints
            if time in parameters.target_times:
                reserve_stored_energy_up_var = model.get_variable(
                    f"reserves_up_e_{self.name}_{time}"
                ) + model.get_variable(f"automated_res_up_e_{self.name}_{time}")
                reserve_stored_energy_down_var = model.get_variable(
                    f"reserves_down_e_{self.name}_{time}"
                ) + model.get_variable(f"automated_res_down_e_{self.name}_{time}")

                model.add_constraint(stored_energy_var >= minimum_energy + reserve_stored_energy_up_var)
                model.add_constraint(stored_energy_var <= maximum_energy - reserve_stored_energy_down_var)

    def add_objective(
        self,
        model: OptimisationModel,
        time: DateTime,
        price_forecast: float,
        parameters: PortfolioOptimisationParameters,
    ):
        for k in range(self.get_fragment_length()):
            if time in parameters.target_times:
                model.add_objective(
                    self.compute_fragment_prices(time, k, parameters)
                    * model.get_variable(f"{self.name}_power_level_frag_{k}_at_{time}")
                    * parameters.timestep
                )

            else:
                model.add_objective(
                    -(price_forecast - self.compute_fragment_prices(time, k, parameters))
                    * model.get_variable(f"{self.name}_power_level_frag_{k}_at_{time}")
                    * parameters.timestep
                )

    def compute_fragment_prices(
        self,
        time: DateTime,
        category,
        parameters: PortfolioOptimisationParameters,
    ):
        if time in parameters.hydraulic_op_times:
            fragment_data = self._get_fragment_data()
            energy_level = self._get_current_energy_level(parameters)

            marginal_weights = self._calculate_marginal_weights(energy_level)

            return self._calculate_fragment_price(fragment_data[category].price, marginal_weights, time)

    def _get_fragment_data(self):
        return {
            category: FragmentData(volume=self.fragment_volumes[category], price=self.fragment_prices[category])
            for category in range(len(self.fragment_volumes))
        }

    def get_fragment_length(self):
        if not len(self.fragment_volumes) == len(self.fragment_prices):
            raise ValueError("Fragment volumes and prices has to be same length")
        return len(self.fragment_volumes)

    def _get_current_energy_level(self: HydroPO, parameters: PortfolioOptimisationParameters) -> float:
        """Get the current energy level from forecast or initial level."""
        energy_forecast = self.stored_energy.get_forecast(
            parameters.execution_date,
            parameters.start_date - parameters.timestep,
            parameters.start_date - parameters.timestep,
        )

        if len(energy_forecast) > 0:
            return energy_forecast.get_value(parameters.start_date - parameters.timestep)
        else:
            return self.initial_level.get_value(parameters.start_date - parameters.timestep)

    def _calculate_marginal_weights(self, energy_level: float) -> dict:
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
            marginal_adjustment = marginal_weights["level_sup"].get_value(time)
        elif marginal_weights["has_min"] and not marginal_weights["has_max"]:
            # Only lower bound available
            marginal_adjustment = marginal_weights["level_inf"].get_value(time)
        elif marginal_weights["has_min"] and marginal_weights["has_max"]:
            # Both bounds available - interpolate
            p_min = marginal_weights["level_inf"].get_value(time)
            p_max = marginal_weights["level_sup"].get_value(time)
            marginal_adjustment = marginal_weights["weight_inf"] * p_min + marginal_weights["weight_sup"] * p_max
        else:
            # No bounds available
            marginal_adjustment = 0.0

        return base_price + marginal_adjustment

    def get_initial_level(self: HydroPO, parameters: PortfolioOptimisationParameters) -> Timeseries:
        if (
            len(
                self.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.start_date - parameters.timestep,
                    parameters.end_date,
                )
            )
            == 0
        ):
            return (
                self.initial_level.filter([parameters.start_date - parameters.timestep, parameters.end_date])
                if isinstance(self.initial_level, Timeseries)
                else self.initial_level.filter(
                    [parameters.start_date - parameters.timestep, parameters.end_date]
                ).collect()
            )
        else:
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
                    self.initial_level.filter([parameters.start_date - parameters.timestep, parameters.end_date])
                    if isinstance(self.initial_level, Timeseries)
                    else self.initial_level.filter(
                        [parameters.start_date - parameters.timestep, parameters.end_date]
                    ).collect()
                )


class FragmentData(BaseModel):
    """Data structure to hold fragment volume and price information."""

    volume: float
    price: float
