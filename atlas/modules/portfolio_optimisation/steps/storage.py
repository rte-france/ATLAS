"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.enums import StorageType
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.steps.base import AbstractOptimStep
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class StoragePOStep(AbstractOptimStep[StoragePO]):
    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        nbr_fragment: int = parameters.storage_mapping[eq.storage_type]["nb_fragment"]

        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding variables for storage unit {eq.name} at time {time}")
            min_power = eq.minimum_power.get_value(time)
            max_power = eq.maximum_power.get_value(time)
            maximum_energy = eq.maximum_energy.get_value(time)
            maximum_automated = get_maximum_automated(eq)

            model.add_continuous_variable(
                name=f"{eq.name}_power_level_sell_{time}", lower_bound=0, upper_bound=max_power
            )
            model.add_continuous_variable(
                name=f"{eq.name}_power_level_buy_{time}", lower_bound=min_power, upper_bound=0
            )
            model.add_boolean_variable(name=f"{eq.name}_is_sell_{time}")
            model.add_continuous_variable(
                name=f"{eq.name}_stored_energy_{time}",
                lower_bound=eq.minimum_state_of_charge.get_value(time) * maximum_energy,
                upper_bound=maximum_energy,
            )

            for n in range(nbr_fragment):
                model.add_continuous_variable(
                    name=f"{eq.name}_power_level_sell_n_{n}_time_{time}", lower_bound=0, upper_bound=max_power
                )
                model.add_continuous_variable(
                    name=f"{eq.name}_power_level_buy_n_{n}_time_{time}", lower_bound=min_power, upper_bound=0
                )

            add_reserve_variables(
                model,
                eq.name,
                time,
                min_power,
                max_power,
                maximum_automated,
                relaxed_reserves=False,
                storage_equipment=True,
                thermal_equipment=False,
            )

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        if eq.maximum_energy.max() <= 0:
            cfg.logger.debug(f"Skipping constraints for storage unit {eq.name} - maximum energy is 0")
            return

        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding constraints for storage unit {eq.name} at time {time}")
            prev_time = time - parameters.temporal.timestep

            automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{eq.name}_{time}")
            automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{eq.name}_{time}")
            reserves_up_var = model.get_variable(f"reserves_up_{eq.name}_{time}")
            reserves_down_var = model.get_variable(f"reserves_down_{eq.name}_{time}")
            unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{eq.name}_{time}")
            unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{eq.name}_{time}")
            power_level_sell_var = model.get_variable(f"{eq.name}_power_level_sell_{time}")
            power_level_buy_var = model.get_variable(f"{eq.name}_power_level_buy_{time}")
            stored_energy_var = model.get_variable(f"{eq.name}_stored_energy_{time}")
            is_sell_var = model.get_variable(f"{eq.name}_is_sell_{time}")

            min_power = eq.minimum_power.get_value(time)
            max_power = eq.maximum_power.get_value(time)
            max_energy = eq.maximum_energy.get_value(time)
            max_energy_previous = eq.maximum_energy.get_value(prev_time)
            maximum_automated = get_maximum_automated(eq)

            if time not in parameters.target_times:
                nb_fragment = parameters.storage_mapping[eq.storage_type]["nb_fragment"]
                for n in range(0, nb_fragment):
                    power_level_sell_n_var = model.get_variable(f"{eq.name}_power_level_sell_n_{n}_time_{time}")
                    power_level_buy_n_var = model.get_variable(f"{eq.name}_power_level_buy_n_{n}_time_{time}")
                    model.add_constraint(
                        power_level_buy_n_var >= min_power / nb_fragment, f"buy_bound_fragment_{n}_{time}_{eq.name}"
                    )
                    model.add_constraint(
                        power_level_sell_n_var <= max_power / nb_fragment, f"sell_bound_fragment_{n}_{time}_{eq.name}"
                    )

                if nb_fragment > 0:
                    model.add_constraint(
                        power_level_sell_var
                        == sum(
                            model.get_variable(f"{eq.name}_power_level_sell_n_{n}_time_{time}")
                            for n in range(0, nb_fragment)
                        ),
                        f"sell_fragment_sum_{time}_{eq.name}",
                    )
                    model.add_constraint(
                        power_level_buy_var
                        == sum(
                            model.get_variable(f"{eq.name}_power_level_buy_n_{n}_time_{time}")
                            for n in range(0, nb_fragment)
                        ),
                        f"buy_fragment_sum_{time}_{eq.name}",
                    )

            model.add_constraint(
                automated_reserves_up_var <= maximum_automated, f"automated_reserves_up_max_{time}_{eq.name}"
            )
            model.add_constraint(
                automated_reserves_down_var <= maximum_automated, f"automated_reserves_down_max_{time}_{eq.name}"
            )
            model.add_constraint(reserves_up_var <= max_power, f"reserves_up_max_{time}_{eq.name}")
            model.add_constraint(reserves_down_var <= max_power, f"reserves_down_max_{time}_{eq.name}")

            if eq.storage_type in [StorageType.BATTERY, StorageType.PUMPED_HYDRAULIC_STORAGE]:
                reserve_stored_energy_down = (
                    reserves_down_var * parameters.battery_reserve_duration.total_hours()
                    + automated_reserves_down_var * parameters.battery_automated_reserve_duration.total_hours()
                )
                reserve_stored_energy_up = (
                    reserves_up_var * parameters.battery_reserve_duration.total_hours()
                    + automated_reserves_up_var * parameters.battery_automated_reserve_duration.total_hours()
                )
                model.add_constraint(
                    power_level_sell_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
                    <= max_power * eq.discharge_efficiency,
                    f"generic_power_max_{time}_{eq.name}",
                )
                model.add_constraint(
                    power_level_buy_var - reserves_down_var - automated_reserves_down_var - unprovided_reserves_down_var
                    >= min_power / eq.charge_efficiency,
                    f"generic_power_min_{time}_{eq.name}",
                )
                model.add_constraint(
                    power_level_sell_var <= max_power * eq.discharge_efficiency * is_sell_var,
                    f"relative_power_max_{time}_{eq.name}",
                )
                model.add_constraint(
                    power_level_buy_var >= min_power * (1 - is_sell_var) / eq.charge_efficiency,
                    f"relative_power_min_{time}_{eq.name}",
                )

            elif eq.storage_type == StorageType.ELECTRIC_VEHICLE:
                reserve_stored_energy_down = (
                    reserves_down_var * parameters.battery_reserve_duration.total_hours()
                    + automated_reserves_down_var * parameters.battery_automated_reserve_duration.total_hours()
                )
                reserve_stored_energy_up = (
                    reserves_up_var * parameters.battery_reserve_duration.total_hours()
                    + automated_reserves_up_var * parameters.battery_automated_reserve_duration.total_hours()
                )
                model.add_constraint(
                    (power_level_sell_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var)
                    <= (eq.is_v2g * max_power * eq.discharge_efficiency),
                    f"generic_power_max_{time}_{eq.name}",
                )
                model.add_constraint(
                    (
                        power_level_buy_var
                        - reserves_down_var
                        - automated_reserves_down_var
                        - unprovided_reserves_down_var
                    )
                    >= min_power / eq.charge_efficiency,
                    f"generic_power_min_{time}_{eq.name}",
                )

            if not eq.displacement_energy:
                displacement_energy = 0
                displacement_energy_prev = 0
            else:
                displacement_energy = int(eq.displacement_energy.get_value(time))
                displacement_energy_prev = int(eq.displacement_energy.get_value(prev_time))

            if time == parameters.temporal.start_date:
                model.add_constraint(
                    stored_energy_var
                    == eq.get_initial_stock(parameters) * max_energy / max_energy_previous
                    - power_level_buy_var * eq.charge_efficiency * parameters.temporal.timestep.total_hours()
                    - power_level_sell_var * parameters.temporal.timestep.total_hours() / eq.discharge_efficiency
                    + (displacement_energy - displacement_energy_prev),
                    f"storage_level_evol_{time}_{eq.name}",
                )
            else:
                stored_energy_prev_var = model.get_variable(f"{eq.name}_stored_energy_{prev_time}")
                model.add_constraint(
                    stored_energy_var
                    == stored_energy_prev_var * max_energy / max_energy_previous
                    - power_level_buy_var * eq.charge_efficiency * parameters.temporal.timestep.total_hours()
                    - power_level_sell_var * parameters.temporal.timestep.total_hours() / eq.discharge_efficiency
                    + (displacement_energy - displacement_energy_prev),
                    f"storage_level_evol_{time}_{eq.name}",
                )

            model.add_constraint(
                stored_energy_var >= max_energy * eq.minimum_state_of_charge.get_value(time) + reserve_stored_energy_up,
                f"min_storage_level_{time}_{eq.name}",
            )
            model.add_constraint(
                stored_energy_var <= max_energy - reserve_stored_energy_down,
                f"max_storage_level_{time}_{eq.name}",
            )

        self._add_cycle_balance_constraint(model)

    def _add_cycle_balance_constraint(self, model: OptimisationModel):
        eq = self.equipment
        model.add_constraint(
            sum(-model.get_variable(f"{eq.name}_power_level_buy_{time}") for time in eq.optimisation_time_window)
            * eq.charge_efficiency
            == sum(model.get_variable(f"{eq.name}_power_level_sell_{time}") for time in eq.optimisation_time_window)
            / eq.discharge_efficiency,
            f"cycle_balance_{eq.name}",
        )

    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict = {}
    ):
        eq = self.equipment
        if eq.maximum_energy.max() <= 0:
            cfg.logger.debug(f"Skipping objective for storage unit {eq.name} - maximum energy is 0")
            return

        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding objective for storage unit {eq.name} at time {time}")
            price_forecast = price_forecasts.get(time, 0.0)
            power_level_sell_var = model.get_variable(f"{eq.name}_power_level_sell_{time}")
            power_level_buy_var = model.get_variable(f"{eq.name}_power_level_buy_{time}")
            model.add_objective(
                -price_forecast
                * (power_level_buy_var + power_level_sell_var)
                * parameters.temporal.timestep.total_hours()
            )

            if time not in parameters.target_times:
                smoothing_factor = parameters.storage_mapping[eq.storage_type]["smoothing_factor"]
                nb_fragment = parameters.storage_mapping[eq.storage_type]["nb_fragment"]

                for n in range(0, nb_fragment):
                    power_level_sell_n_var = model.get_variable(f"{eq.name}_power_level_sell_n_{n}_time_{time}")
                    power_level_buy_n_var = model.get_variable(f"{eq.name}_power_level_buy_n_{n}_time_{time}")

                    if nb_fragment == 1 and n == 0:
                        model.add_objective(-(power_level_sell_n_var + power_level_buy_n_var) * price_forecast)
                    else:
                        model.add_objective(
                            -power_level_sell_n_var * price_forecast * (1 - n * smoothing_factor / (nb_fragment - 1))
                            - power_level_buy_n_var * price_forecast * (1 + n * smoothing_factor / (nb_fragment - 1))
                        )
