from pendulum import DateTime

from atlas.enum import StorageType
from atlas.models.equipment.storage import Storage
from atlas.modules.portfolio_optimisation.optimisation.variable_builder import add_reserve_variables
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import (
    get_maximum_automated,
    get_maximum_energy,
    get_maximum_power,
    get_minimum_power,
)
from atlas.solver.solver_interface import OptimisationModel


class StoragePO(Storage):
    storage_type: StorageType

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        """Build variables for storage equipment."""

        optimisation_times: list[DateTime] = parameters.storage_mapping[self.storage_type]["optimisation_times"]
        nbr_fragment: int = parameters.storage_mapping[self.storage_type]["fragment"]

        for time in optimisation_times:
            min_power = get_minimum_power(self, time)
            max_power = get_maximum_power(self, time)
            maximum_energy = get_maximum_energy(time)
            maximum_automated = self.maximum_afrr + self.maximum_fcr

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

            # Reserve variables for storage
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

    def add_contraints(
        self,
        time: DateTime,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        This function adds constraints and elements in the objective function related to storage equipments.
        """
        prev_time = time - parameters.timestep

        optimisation_times = parameters.storage_mapping[self.storage_type].get("optimisation_times", [])
        automated_reserves_up_var = model.get_variable(f"automated_res_up_e_{self.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_res_down_e_{self.name}_{time}")
        reserves_up_var = model.get_variable(f"reserves_up_e_{self.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_e_{self.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_e_{self.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_e_{self.name}_{time}")
        power_level_sell_var = model.get_variable(f"{self.name}_power_level_sell_{time}")
        power_level_buy_var = model.get_variable(f"{self.name}_power_level_buy_{time}")
        stored_energy_var = model.get_variable(f"{self.name}_stored_energy_{time}")
        is_sell_var = model.get_variable(f"{self.name}_is_sell_{time}")

        # Avoid equipments that have a maximum_energy of 0 (meaning that they are offline)
        if max(self.maximum_energy.values()) <= 0:
            return None

        # Get max and min power
        max_power = get_maximum_power(self, time)
        min_power = get_minimum_power(self, time)

        # For additional period
        if time not in parameters.target_times:
            nb_fragment = parameters.storage_mapping[self.storage_type]["nb_fragment"]
            for n in range(0, nb_fragment):
                power_level_sell_n_var = model.get_variable(f"{self.name}_power_level_sell_n_{n}_time_{time}")
                power_level_buy_n_var = model.get_variable(f"{self.name}_power_level_buy_n_{n}_time_{time}")

                # Add constraint related to power fragment
                model.add_constraint(power_level_buy_n_var >= min_power / nb_fragment)
                model.add_constraint(power_level_sell_n_var <= max_power / nb_fragment)

            if nb_fragment > 0:
                model.add_constraint(power_level_sell_var == sum(power_level_sell_n_var for n in range(0, nb_fragment)))
                model.add_constraint(power_level_buy_var == sum(power_level_buy_n_var for n in range(0, nb_fragment)))

        model.add_constraint(automated_reserves_up_var <= get_maximum_automated(self))
        model.add_constraint(automated_reserves_down_var <= get_maximum_automated(self))
        model.add_constraint(reserves_up_var <= max_power)
        model.add_constraint(reserves_down_var <= max_power)

        # The power delivered by the equipment is between its maximum power and its minimum power
        # FC: I modify the following, it seems to me that there are confusions between power and energy in some constraints

        if self.storage_type == StorageType.BATTERY or self.storage_type == StorageType.PUMPED_HYDRAULIC_STORAGE:
            reserve_stored_energy_down_ti = reserves_down_var * (
                parameters.battery_reserve_duration
            ) + automated_reserves_down_var * (parameters.automated_battery_reserve_duration)
            reserve_stored_energy_up_ti = reserves_up_var * (
                parameters.battery_reserve_duration
            ) + automated_reserves_up_var * (parameters.automated_battery_reserve_duration)

            model.add_constraint(
                power_level_sell_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
                <= max_power * self.discharge_efficiency
            )
            model.add_constraint(
                power_level_buy_var - reserves_down_var - automated_reserves_down_var - unprovided_reserves_down_var
                >= min_power * 1 / self.charge_efficiency
            )

            model.add_constraint(power_level_sell_var <= max_power * self.discharge_efficiency * is_sell_var)
            model.add_constraint(power_level_buy_var >= min_power * 1 / self.charge_efficiency * (1 - is_sell_var))

        if self.storage_type == StorageType.ELECTRIC_VEHICLE:
            reserve_stored_energy_down_ti = reserves_down_var * (
                parameters.battery_reserve_duration
            ) + automated_reserves_down_var * (parameters.automated_battery_reserve_duration)
            reserve_stored_energy_up_ti = reserves_up_var * (
                parameters.battery_reserve_duration
            ) + automated_reserves_up_var * (parameters.automated_battery_reserve_duration)

            model.add_constraint(
                (power_level_sell_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var)
                <= (self.is_v2g * max_power * self.discharge_efficiency)
            )
            model.add_constraint(
                (power_level_buy_var - reserves_down_var - automated_reserves_down_var - unprovided_reserves_down_var)
                >= min_power * 1 / self.charge_efficiency
            )

        # FC: Here we use the deltas between t and t+1 for displacement_energy and maximum_energy because there is a shift in indexing,
        # It would be much clearer if there were no indexes but simply time series.
        if time == parameters.start_date:
            model.add_constraint(
                stored_energy_var
                == self.initial_stock * (get_maximum_energy(self, time) / get_maximum_energy(self, prev_time))
                - power_level_buy_var * self.charge_efficiency * parameters.timestep
                - power_level_sell_var * parameters.timestep / (60.0 * self.discharge_efficiency)
                + (self.displacement_energy[time] - self.displacement_energy[prev_time])
            )

        elif time in optimisation_times:
            model.add_constraint(
                stored_energy_var
                == self.stored_energy[prev_time]
                * (get_maximum_energy(self, time) / get_maximum_energy(self, prev_time))
                - power_level_buy_var * self.charge_efficiency * parameters.timestep
                - power_level_sell_var * parameters.timestep / (60.0 * self.discharge_efficiency)
                + (self.displacement_energy[time] - self.displacement_energy[prev_time])
            )

        # For any time steps:
        # Respect of minimum and maximum stock constraints
        model.add_constraint(
            stored_energy_var
            >= get_maximum_energy(self, time) * self.minimum_state_of_charge.get_value(time)
            + reserve_stored_energy_up_ti
        )
        model.add_constraint(stored_energy_var <= get_maximum_energy(self, time) - reserve_stored_energy_down_ti)

        if time == parameters.start_date:
            model.add_constraint(
                sum(-power_level_buy_var for _ in optimisation_times) * self.charge_efficiency
                == sum(power_level_sell_var for _ in optimisation_times) / self.discharge_efficiency
            )

    def add_objective(
        self,
        model: OptimisationModel,
        time: DateTime,
        price_forecast: float,
    ):
        power_level_sell_var = model.get_variable(f"{self.name}_power_level_sell_{time}")
        power_level_buy_var = model.get_variable(f"{self.name}_power_level_buy_{time}")

        if max(self.maximum_energy.values()) <= 0:
            return None
        local_op_times = self.parameters.storage_mapping[self.storage_type].get("optimisation_times", [])

        if time not in local_op_times:
            return None

        model.add_objective(price_forecast * (power_level_buy_var + power_level_sell_var) * self.parameters.timestep)
        if time not in self.parameters.target_times:
            smoothing_factor = self.parameters.storage_mapping[self.storage_type]["smoothing_factor"]
            nb_fragment = self.parameters.storage_mapping[self.storage_type]["nb_fragment"]
            for n in range(0, nb_fragment):
                power_level_sell_n_var = model.get_variable(f"{self.name}_power_level_sell_n_{n}_time_{time}")
                power_level_buy_n_var = model.get_variable(f"{self.name}_power_level_buy_n_{n}_time_{time}")

                # The objective function is the total profit over the optimisation period
                if nb_fragment == 1 and n == 0:
                    model.add_objective(
                        -power_level_sell_n_var * price_forecast - power_level_buy_n_var * price_forecast
                    )
                else:
                    model.add_objective(
                        -power_level_sell_n_var * price_forecast * (1 - n * smoothing_factor / (nb_fragment - 1))
                        - power_level_buy_n_var * price_forecast * (1 + n * smoothing_factor / (nb_fragment - 1))
                    )
