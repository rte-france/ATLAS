from pendulum import DateTime

from atlas.enum import StorageType
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.wind import Wind
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.get_fragment_price import _get_fragment_data
from atlas.modules.portfolio_optimisation.utils.getters import (
    get_maximum_automated,
    get_maximum_energy,
    get_maximum_power,
    get_minimum_energy,
    get_minimum_power,
    get_variable_cost,
)
from atlas.solver.solver_interface import OptimisationModel


def add_constraints_hydro(
    time: DateTime,
    hydro_equipments: list[Hydro],
    model: OptimisationModel,
    price_forecast: float,
    parameters: PortfolioOptimisationParameters,
):
    """
    This function formulates the hydraulic reservoir offers.
    """

    for obj in hydro_equipments:
        max_power = get_maximum_power(obj, time)
        min_power = get_minimum_power(obj, time)

        model.add_constraint(model.get_variable(f"relaxed_reserves_{obj.name}_{time}") <= min_power)
        model.add_constraint(
            model.get_variable(f"automated_reserves_up_{obj.name}_{time}") <= get_maximum_automated(obj)
        )
        model.add_constraint(
            model.get_variable(f"automated_reserves_up_{obj.name}_{time}") <= get_maximum_automated(obj)
        )
        model.add_constraint(model.get_variable(f"reserves_up_{obj.name}_{time}") <= max_power)
        model.add_constraint(model.get_variable(f"reserves_up_{obj.name}_{time}") <= max_power)

        # --- Reservoir constraints
        stored_energy_var = model.get_variable(f"{obj.name}_stored_energy_{time}")
        previous_stored_energy_var = model.get_variable(f"{obj.name}_stored_energy_{time - parameters.timestep}")

        power_level_fragment_sum_var = sum(
            model.get_variable(f"{obj.name}_power_level_frag_{category}_at_{time}")
            for category in _get_fragment_data(obj)
        )

        if time == parameters.start_date:
            model.add_constraint(
                stored_energy_var
                == obj.initial_level.get_value(parameters.start_date - parameters.timestep)
                - power_level_fragment_sum_var * parameters.timestep
            )

        elif time in parameters.target_times:
            model.add_constraint(
                stored_energy_var == previous_stored_energy_var - power_level_fragment_sum_var * parameters.timestep
            )

        # For any time steps:
        # Respect of minimum and maximum stock constraints
        if time in parameters.target_times:
            reserve_stored_energy_up_var = model.get_variable(f"reserves_up_e_{obj.name}_{time}") + model.get_variable(
                f"automated_res_up_e_{obj.name}_{time}"
            )
            reserve_stored_energy_down_var = model.get_variable(
                f"reserves_down_e_{obj.name}_{time}"
            ) + model.get_variable(f"automated_res_down_e_{obj.name}_{time}")

            model.add_constraint(stored_energy_var >= get_minimum_energy(obj, time) + reserve_stored_energy_up_var)
            model.add_constraint(stored_energy_var <= get_maximum_energy(obj, time) - reserve_stored_energy_down_var)


def add_constraints_load(
    time: DateTime,
    load_equipments: list[Load],
    model: OptimisationModel,
    price_forecast: float,
    parameters: PortfolioOptimisationParameters,
):
    """
    This function adds constraints and elements in the objective function related to load equipments.
    """

    for obj in load_equipments:
        power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")
        model.add_constraint(power_level_var >= get_maximum_power(obj, time))
        model.add_constraint(power_level_var <= get_minimum_power(obj, time))


def add_constraints_wind_solar(
    time: DateTime,
    equipments: list[Wind | Solar],
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
):
    """
    This function formulates the wind and photovoltaic equipments orders.
    """

    for obj in equipments:
        if time in parameters.op_times:
            max_power = get_maximum_power(obj, time)
            min_power = get_minimum_power(obj, time)

            power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")
            automated_reserves_up_var = model.get_variable(f"automated_res_up_e_{obj.name}_{time}")
            automated_reserves_down_var = model.get_variable(f"automated_res_down_e_{obj.name}_{time}")
            reserves_up_var = model.get_variable(f"reserves_up_e_{obj.name}_{time}")
            reserves_down_var = model.get_variable(f"reserves_down_e_{obj.name}_{time}")

            model.add_objective(get_variable_cost(obj, time) * power_level_var * parameters.timestep)

            model.add_constraint(power_level_var <= max_power)
            model.add_constraint(power_level_var >= min_power)
            model.add_constraint(automated_reserves_up_var <= get_maximum_automated(obj))
            model.add_constraint(automated_reserves_down_var <= get_maximum_automated(obj))
            model.add_constraint(reserves_up_var <= max_power)
            model.add_constraint(reserves_down_var <= max_power)


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
        optimisation_times = parameters.storage_mapping[obj.storage_type].get("optimisation_times", [])
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

        # Get max and min power
        max_power = get_maximum_power(obj, time)
        min_power = get_minimum_power(obj, time)

        # For additional period
        if time not in parameters.target_times:
            nb_fragment = parameters.storage_mapping[obj.storage_type]["nb_fragment"]
            for n in range(0, nb_fragment):
                power_level_sell_n_var = model.get_variable(f"{obj.name}_power_level_sell_n_{n}_time_{time}")
                power_level_buy_n_var = model.get_variable(f"{obj.name}_power_level_buy_n_{n}_time_{time}")

                # Add constraint related to power fragment
                model.add_constraint(power_level_buy_n_var >= min_power / nb_fragment)
                model.add_constraint(power_level_sell_n_var <= max_power / nb_fragment)

            if nb_fragment > 0:
                model.add_constraint(power_level_sell_var == sum(power_level_sell_n_var for n in range(0, nb_fragment)))
                model.add_constraint(power_level_buy_var == sum(power_level_buy_n_var for n in range(0, nb_fragment)))

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

        elif time in optimisation_times:
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

        if time == parameters.start_date:
            model.add_constraint(
                sum(-power_level_buy_var for _ in optimisation_times) * obj.charge_efficiency
                == sum(power_level_sell_var for _ in optimisation_times) / obj.discharge_efficiency
            )
