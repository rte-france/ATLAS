"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime, Duration

import atlas.config as cfg
from atlas.enums import StorageType
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.timeseries import Timeseries
from atlas.objects.equipment.storage import Storage
from atlas.modules.portfolio_optimisation.models.base_equipment import BaseEquipmentPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel


class StoragePO(BaseEquipmentPO, Storage):
    storage_type: StorageType
    maximum_fcr: float
    maximum_afrr: float
    minimum_power: AbstractTimeseries
    maximum_power: AbstractTimeseries
    minimum_state_of_charge: AbstractTimeseries
    discharge_efficiency: float
    charge_efficiency: float
    maximum_energy: AbstractTimeseries
    additional_hours: Duration

    optimisation_time_window: list[DateTime] = []
    _cached_energy_forecast: Timeseries | None = None
    _cached_energy_forecat_initial: Timeseries | None = None

    def add_variables(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        """
        Build variables for storage equipment.

        :param model: Optimization model
        :type model: OptimisationModel
        :param time: Current time period
        :type time: DateTime
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        """

        nbr_fragment: int = parameters.storage_mapping[self.storage_type]["nb_fragment"]

        if time in self.optimisation_time_window:
            cfg.logger.debug(f"Adding variables for storage unit {self.name} at time {time}")
            min_power = self.minimum_power.get_value(time)
            max_power = self.maximum_power.get_value(time)
            maximum_energy = self.maximum_energy.get_value(time)
            maximum_automated = get_maximum_automated(self)

            # Basic storage variables
            model.add_continuous_variable(
                name=f"{self.name}_power_level_sell_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"{self.name}_power_level_buy_{time}",
                lower_bound=min_power,
                upper_bound=0,
            )
            model.add_boolean_variable(
                name=f"{self.name}_is_sell_{time}",
            )
            model.add_continuous_variable(
                name=f"{self.name}_stored_energy_{time}",
                lower_bound=self.minimum_state_of_charge.get_value(time) * maximum_energy,
                upper_bound=maximum_energy,
            )

            # Fragment variables
            for n in range(nbr_fragment):
                model.add_continuous_variable(
                    name=f"{self.name}_power_level_sell_n_{n}_time_{time}",
                    lower_bound=0,
                    upper_bound=max_power,
                )
                model.add_continuous_variable(
                    name=f"{self.name}_power_level_buy_n_{n}_time_{time}",
                    lower_bound=min_power,
                    upper_bound=0,
                )

            add_reserve_variables(
                model,
                self.name,
                time,
                min_power,
                max_power,
                maximum_automated,
                relaxed_reserves=False,
                storage_equipment=True,
                thermal_equipment=False,
            )
        else:
            cfg.logger.debug(f"Skipping variables for storage unit {self.name} at non-optimization time {time}")

    def add_constraints(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        This function adds constraints and elements in the objective function related to storage equipments.
        """
        if self.maximum_energy.max() <= 0:
            cfg.logger.debug(f"Skipping constraints for storage unit {self.name} - maximum energy is 0")
            return None

        if time in self.optimisation_time_window:
            cfg.logger.debug(f"Adding constraints for storage unit {self.name} at time {time}")
            prev_time = time - parameters.temporal.timestep

            automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.name}_{time}")
            automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.name}_{time}")
            reserves_up_var = model.get_variable(f"reserves_up_{self.name}_{time}")
            reserves_down_var = model.get_variable(f"reserves_down_{self.name}_{time}")
            unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.name}_{time}")
            unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.name}_{time}")
            power_level_sell_var = model.get_variable(f"{self.name}_power_level_sell_{time}")
            power_level_buy_var = model.get_variable(f"{self.name}_power_level_buy_{time}")
            stored_energy_var = model.get_variable(f"{self.name}_stored_energy_{time}")

            is_sell_var = model.get_variable(f"{self.name}_is_sell_{time}")

            min_power = self.minimum_power.get_value(time)
            max_power = self.maximum_power.get_value(time)
            max_energy = self.maximum_energy.get_value(time)
            max_energy_previous = self.maximum_energy.get_value(prev_time)
            maximum_automated = get_maximum_automated(self)

            # For additional period
            if time not in parameters.target_times:
                nb_fragment = parameters.storage_mapping[self.storage_type]["nb_fragment"]
                for n in range(0, nb_fragment):
                    power_level_sell_n_var = model.get_variable(f"{self.name}_power_level_sell_n_{n}_time_{time}")
                    power_level_buy_n_var = model.get_variable(f"{self.name}_power_level_buy_n_{n}_time_{time}")

                    # Add constraint related to power fragment
                    model.add_constraint(
                        power_level_buy_n_var >= min_power / nb_fragment, f"buy_bound_fragment_{n}_{time}_{self.name}"
                    )
                    model.add_constraint(
                        power_level_sell_n_var <= max_power / nb_fragment, f"sell_bound_fragment_{n}_{time}_{self.name}"
                    )

                if nb_fragment > 0:
                    model.add_constraint(
                        power_level_sell_var
                        == sum(
                            model.get_variable(f"{self.name}_power_level_sell_n_{n}_time_{time}")
                            for n in range(0, nb_fragment)
                        ),
                        f"sell_fragment_sum_{time}_{self.name}",
                    )
                    model.add_constraint(
                        power_level_buy_var
                        == sum(
                            model.get_variable(f"{self.name}_power_level_buy_n_{n}_time_{time}")
                            for n in range(0, nb_fragment)
                        ),
                        f"buy_fragment_sum_{time}_{self.name}",
                    )

            model.add_constraint(
                automated_reserves_up_var <= maximum_automated, f"automated_reserves_up_max_{time}_{self.name}"
            )
            model.add_constraint(
                automated_reserves_down_var <= maximum_automated, f"automated_reserves_down_max_{time}_{self.name}"
            )
            model.add_constraint(reserves_up_var <= max_power, f"reserves_up_max_{time}_{self.name}")
            model.add_constraint(reserves_down_var <= max_power, f"reserves_down_max_{time}_{self.name}")

            if self.storage_type in [StorageType.BATTERY, StorageType.PUMPED_HYDRAULIC_STORAGE]:
                reserve_stored_energy_down = reserves_down_var * (
                    parameters.battery_reserve_duration.total_hours()
                ) + automated_reserves_down_var * (parameters.battery_automated_reserve_duration.total_hours())
                reserve_stored_energy_up = reserves_up_var * (
                    parameters.battery_reserve_duration.total_hours()
                ) + automated_reserves_up_var * (parameters.battery_automated_reserve_duration.total_hours())

                model.add_constraint(
                    power_level_sell_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
                    <= max_power * self.discharge_efficiency,
                    f"generic_power_max_{time}_{self.name}",
                )
                model.add_constraint(
                    power_level_buy_var - reserves_down_var - automated_reserves_down_var - unprovided_reserves_down_var
                    >= min_power / self.charge_efficiency,
                    f"generic_power_min_{time}_{self.name}",
                )

                model.add_constraint(
                    power_level_sell_var <= max_power * self.discharge_efficiency * is_sell_var,
                    f"relative_power_max_{time}_{self.name}",
                )
                model.add_constraint(
                    power_level_buy_var >= min_power * (1 - is_sell_var) / self.charge_efficiency,
                    f"relative_power_min_{time}_{self.name}",
                )

            elif self.storage_type == StorageType.ELECTRIC_VEHICLE:
                reserve_stored_energy_down = reserves_down_var * (
                    parameters.battery_reserve_duration.total_hours()
                ) + automated_reserves_down_var * (parameters.battery_automated_reserve_duration.total_hours())
                reserve_stored_energy_up = reserves_up_var * (
                    parameters.battery_reserve_duration.total_hours()
                ) + automated_reserves_up_var * (parameters.battery_automated_reserve_duration.total_hours())

                model.add_constraint(
                    (power_level_sell_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var)
                    <= (self.is_v2g * max_power * self.discharge_efficiency),
                    f"generic_power_max_{time}_{self.name}",
                )
                model.add_constraint(
                    (
                        power_level_buy_var
                        - reserves_down_var
                        - automated_reserves_down_var
                        - unprovided_reserves_down_var
                    )
                    >= min_power / self.charge_efficiency,
                    f"generic_power_min_{time}_{self.name}",
                )
            if not self.displacement_energy:
                displacement_energy = 0
                displacement_energy_prev = 0
            else:
                displacement_energy = int(self.displacement_energy.get_value(time))
                displacement_energy_prev = int(self.displacement_energy.get_value(prev_time))

            if time == parameters.temporal.start_date:
                model.add_constraint(
                    stored_energy_var
                    == self.get_initial_stock(parameters) * max_energy / max_energy_previous
                    - power_level_buy_var * self.charge_efficiency * parameters.temporal.timestep.total_hours()
                    - power_level_sell_var * parameters.temporal.timestep.total_hours() / self.discharge_efficiency
                    + (displacement_energy - displacement_energy_prev),
                    f"storage_level_evol_{time}_{self.name}",
                )

            else:
                stored_energy_prev_var = model.get_variable(f"{self.name}_stored_energy_{prev_time}")

                model.add_constraint(
                    stored_energy_var
                    == stored_energy_prev_var * max_energy / max_energy_previous
                    - power_level_buy_var * self.charge_efficiency * parameters.temporal.timestep.total_hours()
                    - power_level_sell_var * parameters.temporal.timestep.total_hours() / self.discharge_efficiency
                    + (displacement_energy - displacement_energy_prev),
                    f"storage_level_evol_{time}_{self.name}",
                )

            model.add_constraint(
                stored_energy_var
                >= max_energy * self.minimum_state_of_charge.get_value(time) + reserve_stored_energy_up,
                f"min_storage_level_{time}_{self.name}",
            )
            model.add_constraint(
                stored_energy_var <= max_energy - reserve_stored_energy_down,
                f"max_storage_level_{time}_{self.name}",
            )
        else:
            cfg.logger.debug(f"Skipping constraints for storage unit {self.name} at non-optimization time {time}")

    def add_objective(
        self,
        model: OptimisationModel,
        time: DateTime,
        price_forecast: float,
        parameters: PortfolioOptimisationParameters,
    ):
        if self.maximum_energy.max() <= 0:
            cfg.logger.debug(f"Skipping objective for storage unit {self.name} - maximum energy is 0")
            return None

        if time in self.optimisation_time_window:
            cfg.logger.debug(f"Adding objective for storage unit {self.name} at time {time}")
            power_level_sell_var = model.get_variable(f"{self.name}_power_level_sell_{time}")
            power_level_buy_var = model.get_variable(f"{self.name}_power_level_buy_{time}")
            model.add_objective(
                -price_forecast
                * (power_level_buy_var + power_level_sell_var)
                * parameters.temporal.timestep.total_hours(),
            )

            if time not in parameters.target_times:
                smoothing_factor = parameters.storage_mapping[self.storage_type]["smoothing_factor"]
                nb_fragment = parameters.storage_mapping[self.storage_type]["nb_fragment"]

                for n in range(0, nb_fragment):
                    power_level_sell_n_var = model.get_variable(f"{self.name}_power_level_sell_n_{n}_time_{time}")
                    power_level_buy_n_var = model.get_variable(f"{self.name}_power_level_buy_n_{n}_time_{time}")

                    if nb_fragment == 1 and n == 0:
                        model.add_objective(
                            -(power_level_sell_n_var + power_level_buy_n_var) * price_forecast,
                        )
                    else:
                        model.add_objective(
                            -power_level_sell_n_var * price_forecast * (1 - n * smoothing_factor / (nb_fragment - 1))
                            - power_level_buy_n_var * price_forecast * (1 + n * smoothing_factor / (nb_fragment - 1)),
                        )
        else:
            cfg.logger.debug(
                f"Skipping objective for storage unit {self.name} at time {time} - not in optimization times or target times"
            )

    def add_cycle_balance_constraint(self, model: OptimisationModel):
        model.add_constraint(
            sum(-model.get_variable(f"{self.name}_power_level_buy_{time}") for time in self.optimisation_time_window)
            * self.charge_efficiency
            == sum(model.get_variable(f"{self.name}_power_level_sell_{time}") for time in self.optimisation_time_window)
            / self.discharge_efficiency,
            f"cycle_balance_{self.name}",
        )

    def get_initial_stock(self, parameters: PortfolioOptimisationParameters) -> float:
        default_energy = (
            self.maximum_energy.get_value(parameters.temporal.start_date - parameters.temporal.timestep)
            * self.storage_initial_level
        )

        if self.stored_energy is None or not self._cached_energy_forecat_initial:
            return default_energy

        if self._cached_energy_forecast:
            return self._cached_energy_forecast.dataframe.select("time").head(1).item()

        return default_energy

    def prefetch_forecasts(self, execution_date: DateTime, init_battery_time: DateTime):
        """
        Pre-fetch and cache forecasts for the entire optimization time window.

        :param execution_date: Execution date for forecasts
        :type execution_date: DateTime
        :param init_battery_time: Initial battery time
        :type init_battery_time: DateTime
        """
        if self.stored_energy:
            self._cached_energy_forecat_initial = self.stored_energy.get_forecast(
                execution_date, init_battery_time.subtract(days=2), init_battery_time
            )
            self._cached_energy_forecast = self.stored_energy.get_forecast(
                execution_date, init_battery_time, init_battery_time
            )
