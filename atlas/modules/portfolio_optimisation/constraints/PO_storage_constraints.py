from pendulum import DateTime

from atlas.enum import StorageType
from atlas.models.equipment.storage import Storage
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import (
    get_maximum_automated,
    get_maximum_energy,
    get_maximum_power,
    get_minimum_power,
)
from atlas.solver.solver_interface import OptimisationModel


def add_contraints_storage(
    time: DateTime,
    storage_equipments: list[Storage],
    model: OptimisationModel,
    price_forecast: float,
    parameters: PortfolioOptimisationParameters,
):
    """
    This function adds constraints and elements in the objective function related to storage equipments.
    """
    # Preload useful variables to avoid excessive call to functions or method
    prev_time = time - parameters.timestep

    for obj in storage_equipments:
        automated_reserves_up_var = model.get_variable(f"automated_res_up_e_{obj.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_res_down_e_{obj.name}_{time}")
        reserves_up_var = model.get_variable(f"reserves_up_e_{obj.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_e_{obj.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_e_{obj.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_e_{obj.name}_{time}")
        power_level_sell_var = model.get_variable(f"{obj.name}_power_level_sell_{time}")
        power_level_buy_var = model.get_variable(f"{obj.name}_power_level_buy_{time}")
        stored_energy_var = model.get_variable(f"{obj.name}_stored_energy_{time}")
        is_sell_var = model.get_variable(f"{obj.name}_is_sell_{time}")

        # Avoid equipments that have a maximum_energy of 0 (meaning that they are offline)
        if max(obj.maximum_energy.values()) <= 0:
            continue

        if obj.storage_type == StorageType.BATTERY:
            local_op_times = parameters.battery_op_times
        elif obj.storage_type == StorageType.PUMPED_HYDRAULIC_STORAGE:
            local_op_times = parameters.phs_op_times
        elif obj.storage_type == StorageType.ELECTRIC_VEHICLE:
            local_op_times = parameters.ev_op_times
        if time not in local_op_times:
            continue

        # Get max and min power
        max_power = get_maximum_power(obj, time)
        min_power = get_minimum_power(obj, time)

        model.add_objective(price_forecast * (power_level_buy_var + power_level_sell_var) * parameters.timestep)

        # For additional period
        if time not in parameters.target_times:
            if obj.storage_type == StorageType.BATTERY:
                nbr_fragment = parameters.battery_nb_fragments
                smoothing_factor = parameters.battery_smoothing_factor

            elif obj.storage_type == StorageType.ELECTRIC_VEHICLE:
                nbr_fragment = parameters.ev_nb_fragments
                smoothing_factor = parameters.ev_smoothing_factor

            else:
                nbr_fragment = parameters.phs_nb_fragments
                smoothing_factor = parameters.phs_smoothing_factor

            for n in range(0, nbr_fragment):
                power_level_sell_n_var = model.get_variable(f"{obj.name}_power_level_sell_n_{n}_time_{time}")
                power_level_buy_n_var = model.get_variable(f"{obj.name}_power_level_buy_n_{n}_time_{time}")

                # The objective function is the total profit over the optimisation period
                if nbr_fragment == 1 and n == 0:
                    model.add_objective(
                        -power_level_sell_n_var * price_forecast - power_level_buy_n_var * price_forecast
                    )
                else:
                    model.add_objective(
                        -power_level_sell_n_var * price_forecast * (1 - n * smoothing_factor / (nbr_fragment - 1))
                        - power_level_buy_n_var * price_forecast * (1 + n * smoothing_factor / (nbr_fragment - 1))
                    )

                # Add constraint related to power fragment
                model.add_constraint(power_level_buy_n_var >= min_power / nbr_fragment)
                model.add_constraint(power_level_sell_n_var <= max_power / nbr_fragment)

            if nbr_fragment > 0:
                model.add_constraint(
                    power_level_sell_var == sum(power_level_sell_n_var for n in range(0, nbr_fragment))
                )
                model.add_constraint(power_level_buy_var == sum(power_level_buy_n_var for n in range(0, nbr_fragment)))

        model.add_constraint(automated_reserves_up_var <= get_maximum_automated(obj))
        model.add_constraint(automated_reserves_down_var <= get_maximum_automated(obj))
        model.add_constraint(reserves_up_var <= max_power)
        model.add_constraint(reserves_down_var <= max_power)

        # The power delivered by the equipment is between its maximum power and its minimum power
        # FC: I modify the following, it seems to me that there are confusions between power and energy in some constraints

        if obj.storage_type == StorageType.BATTERY or obj.storage_type == StorageType.PUMPED_HYDRAULIC_STORAGE:
            reserve_stored_energy_down_ti = reserves_down_var * (
                parameters.battery_reserve_duration
            ) + automated_reserves_down_var * (parameters.automated_battery_reserve_duration)
            reserve_stored_energy_up_ti = reserves_up_var * (
                parameters.battery_reserve_duration
            ) + automated_reserves_up_var * (parameters.automated_battery_reserve_duration)

            model.add_constraint(
                power_level_sell_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
                <= max_power * obj.discharge_efficiency
            )
            model.add_constraint(
                power_level_buy_var - reserves_down_var - automated_reserves_down_var - unprovided_reserves_down_var
                >= min_power * 1 / obj.charge_efficiency
            )

            model.add_constraint(power_level_sell_var <= max_power * obj.discharge_efficiency * is_sell_var)
            model.add_constraint(power_level_buy_var >= min_power * 1 / obj.charge_efficiency * (1 - is_sell_var))

        if obj.storage_type == StorageType.ELECTRIC_VEHICLE:
            reserve_stored_energy_down_ti = reserves_down_var * (
                parameters.battery_reserve_duration
            ) + automated_reserves_down_var * (parameters.automated_battery_reserve_duration)
            reserve_stored_energy_up_ti = reserves_up_var * (
                parameters.battery_reserve_duration
            ) + automated_reserves_up_var * (parameters.automated_battery_reserve_duration)

            model.add_constraint(
                (power_level_sell_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var)
                <= (obj.is_v2g * max_power * obj.discharge_efficiency)
            )
            model.add_constraint(
                (power_level_buy_var - reserves_down_var - automated_reserves_down_var - unprovided_reserves_down_var)
                >= min_power * 1 / obj.charge_efficiency
            )

        # FC: Here we use the deltas between t and t+1 for displacement_energy and maximum_energy because there is a shift in indexing,
        # It would be much clearer if there were no indexes but simply time series.
        if time == parameters.start_date:
            model.add_constraint(
                stored_energy_var
                == obj.initial_stock * (get_maximum_energy(obj, time) / get_maximum_energy(obj, prev_time))
                - power_level_buy_var * obj.charge_efficiency * parameters.timestep
                - power_level_sell_var * parameters.timestep / (60.0 * obj.discharge_efficiency)
                + (obj.displacement_energy[time] - obj.displacement_energy[prev_time])
            )

        elif time in local_op_times:
            model.add_constraint(
                stored_energy_var
                == obj.stored_energy[prev_time] * (get_maximum_energy(obj, time) / get_maximum_energy(obj, prev_time))
                - power_level_buy_var * obj.charge_efficiency * parameters.timestep
                - power_level_sell_var * parameters.timestep / (60.0 * obj.discharge_efficiency)
                + (obj.displacement_energy[time] - obj.displacement_energy[prev_time])
            )

        # For any time steps:
        # Respect of minimum and maximum stock constraints
        model.add_constraint(
            stored_energy_var
            >= get_maximum_energy(obj, time) * obj.minimum_state_of_charge.get_value(time) + reserve_stored_energy_up_ti
        )
        model.add_constraint(stored_energy_var <= get_maximum_energy(obj, time) - reserve_stored_energy_down_ti)

        # Global cycle balance (the reservoir level of the equipment remains
        # identical between the first and last dates of the optimization period)
        if time == parameters.start_date:
            model.add_constraint(
                sum(-power_level_buy_var for _ in local_op_times) * obj.charge_efficiency
                == sum(power_level_sell_var for _ in local_op_times) / obj.discharge_efficiency
            )
