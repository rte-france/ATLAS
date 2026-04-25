"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.steps.base import EquipmentPOStep
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class HydroPOStep(EquipmentPOStep[HydroPO]):
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
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict = {}
    ):
        eq = self.equipment
        energy_level = eq._get_current_energy_level(parameters)
        marginal_weights = eq._calculate_marginal_weights(energy_level)

        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding objective for hydro unit {eq.name} at time {time}")
            price_forecast = price_forecasts.get(time, 0.0)

            for k in range(len(eq.fragment_data.keys())):
                fragment_price = eq._calculate_fragment_price(eq.fragment_data[k].price, marginal_weights, time)
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
