from pendulum import DateTime

from atlas.enum import StorageType
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.wind import Wind
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


def add_variables_hydro(
    time: DateTime,
    equipments: list[Hydro],
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
):
    for obj in equipments:
        if len(
            (
                obj.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.start_date - parameters.timestep,
                    parameters.end_date,
                )
            )
            == 0
        ):
            obj.initial_level = obj.initial_level.filter(
                [parameters.start_date - parameters.timestep, parameters.end_date]
            )
        else:
            if (
                obj.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.start_date - parameters.timestep,
                    parameters.end_date,
                ).first_date()
                < parameters.start_date
            ):
                obj.initial_level = obj.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.start_date - parameters.timestep,
                    parameters.end_date,
                )

            else:
                obj.initial_level = obj.initial_level.filter(
                    [parameters.start_date - parameters.timestep, parameters.end_date]
                )

        t0_minus_delta_t = parameters.hydraulic_op_times[0] - parameters.timestep
        power = obj.power.get_forecast(parameters.execution_date, t0_minus_delta_t, parameters.start_date)

        for idx, time in enumerate(parameters.hydraulic_op_times):
            min_power = obj.minimum_power.get_value(time)
            max_power = obj.maximum_power.get_value(time)
            max_energy = obj.maximum_energy.get_value(time)

            obj.power_level[time] = model.add_continuous_variable(
                name=f"{obj.name}_power_level_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            obj.stored_energy[time] = model.add_continuous_variable(
                name=f"{obj.name}_stored_energy_{idx}",
                lower_bound=0,
                upper_bound=max_energy,
            )
            _get_fragment_price_and_size(obj, time, parameters, model)

            maximum_automated = obj.maximum_afrr + obj.maximum_fcr

            # Optimisation Variables related to reserves
            obj.reserves_up[time] = model.add_continuous_variable(
                name=f"reserves_up_e_{obj.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            obj.reserves_down[time] = model.add_continuous_variable(
                name=f"reserves_down_e_{obj.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            obj.unprovided_reserves_up[time] = model.add_continuous_variable(
                name=f"unprovided_reserves_up_e_{obj.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            obj.unprovided_reserves_down[time] = model.add_continuous_variable(
                name=f"unprovided_reserves_down_e_{obj.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            obj.relaxed_reserves[time] = model.add_continuous_variable(
                name=f"relaxed_reservese_{obj.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=0,
            )
            obj.automated_reserves_up[time] = model.add_continuous_variable(
                name=f"automated_res_up_e_{obj.name}_at_{idx}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            obj.automated_reserves_down[time] = model.add_continuous_variable(
                name=f"automated_res_down_e_{obj.name}_at_{idx}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            obj.contracted_difference_up[time] = model.add_continuous_variable(
                name=f"contracted_diff_up_e_{obj.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            obj.contracted_difference_down[time] = model.add_continuous_variable(
                name=f"contracted_diff_down_e_{obj.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            obj.automated_contracted_difference_up[time] = model.add_continuous_variable(
                name=f"automated_contracted_diff_up_e_{obj.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            obj.automated_contracted_difference_down[time] = model.add_continuous_variable(
                name=f"automated_contracted_diff_down_e_{obj.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )


def add_variables_solar_wind(
    time: DateTime,
    equipments: list[Solar | Wind],
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
):
    for obj in equipments:
        for idx, time in enumerate(parameters.target_times):
            max_power = obj.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)

            min_power = (1 - obj.maximum_curtailment_ratio.get_value(time)) * max_power

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )

            maximum_automated = obj.maximum_afrr + obj.maximum_fcr

            model.add_continuous_variable(
                name=f"reserves_up_e_{obj.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"reserves_down_e_{obj.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"unprovided_reserves_up_e_{obj.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"unprovided_reserves_down_e_{obj.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_reserves_up_e_{obj.name}_at_{idx}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"automated_reserves_down_e_{obj.name}_at_{idx}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"contracted_diff_up_e_{obj.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"contracted_diff_down_e_{obj.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_contracted_diff_up_e_{obj.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_contracted_diff_down_e_{obj.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )


def add_variables_storage(
    time: DateTime,
    equipments: list[Storage],
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
):
    MAPPING_STORAGE_TYPE_OPTIMISATION_TIMES = {
        StorageType.BATTERY: {
            "op_time_frame": parameters.battery_op_times,
            "fragment": parameters.battery_number_of_fragments,
        },
        StorageType.PUMPED_HYDRAULIC_STORAGE: {
            "op_time_frame": parameters.phs_op_times,
            "fragment": parameters.pumped_hydraulic_number_of_fragments,
        },
        StorageType.ELECTRIC_VEHICLE: {
            "op_time_frame": parameters.ev_op_times,
            "fragment": parameters.electric_vehicle_number_of_fragments,
        },
    }

    for obj in equipments:
        if (
            len(
                obj.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.init_battery_time.subtract(days=2),
                    parameters.init_battery_time,
                )
            )
            == 0
        ):
            obj.initial_stock = obj.maximum_energy.get_value(
                (parameters.start_date - parameters.timestep) * obj.storage_initial_level,
            )

        else:
            obj.initial_stock = (
                obj.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.init_battery_time,
                    parameters.init_battery_time,
                )
                .dataframe.select("time")
                .to_series()
                .to_list()[0]
            )

        op_time_frame = MAPPING_STORAGE_TYPE_OPTIMISATION_TIMES[obj.storage_type]["op_time_frame"]
        for idx, time in enumerate(op_time_frame):
            max_power = obj.maximum_power.get_value(time)
            if obj.minimum_power or len(obj.minimum_power) == 0:
                min_power = -max_power
            else:
                min_power = obj.minimum_power.get_value(time)

            maximum_energy = obj.maximum_energy.get_value(time)
            min_state_of_charge = obj.minimum_state_of_charge.get_value(time)

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_sell_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_buy_{idx}",
                lower_bound=min_power,
                upper_bound=0,
            )

            model.add_boolean_variable(
                name=f"{obj.name}_is_sell_{idx}",
            )

            model.add_continuous_variable(
                name=f"{obj.name}_stored_energy_{idx}",
                lower_bound=min_state_of_charge * maximum_energy,
                upper_bound=maximum_energy,
            )

            maximum_automated = obj.maximum_afrr + obj.maximum_fcr

            nbr_fragment = MAPPING_STORAGE_TYPE_OPTIMISATION_TIMES[obj.storage_type]["fragment"]

            for n in range(0, nbr_fragment):
                model.add_continuous_variable(
                    name=f"{obj.name}_power_level_sell_n_{n}_time_{idx}",
                    lower_bound=0,
                    upper_bound=max_power,
                )
                model.add_continuous_variable(
                    name=f"{obj.name}_power_level_buy_n_{n}_time_{idx}",
                    lower_bound=min_power,
                    upper_bound=0,
                )

            model.add_continuous_variable(
                name=f"reserves_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"reserves_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"unprovided_reserves_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"unprovided_reserves_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_reserves_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"automated_reserves_down_e_{obj.name}_at_{time}",
                lower_bound=-maximum_automated,
                upper_bound=maximum_automated,
            )


def add_variables_load(
    time: DateTime,
    equipments: list[Load],
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
):
    for obj in equipments:
        for idx, time in enumerate(parameters.target_times):
            max_power = obj.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)

            model.add_continuous_variable(
                f"{obj.name}_power_level_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )


def _get_fragment_price_and_size(
    obj: Hydro, time: DateTime, parameters: PortfolioOptimisationParameters, model: OptimisationModel
):
    """
    This function formulates the hydraulic reservoir offers.

    Arguments:
    - `input_marker`: an input marker
    - `output_marker`: an output marker
    - `orders_time`: a list of dates at which orders must be formulated.
    """

    delta_wu = {}
    for category in range(len(obj.fragment_volumes)):
        delta_wu[category] = (
            obj.fragment_volumes[category],
            obj.fragment_prices[category],
        )

    energy_forecast = obj.stored_energy.get_forecast(
        parameters.execution_date,
        parameters.start_date - parameters.timestep,
        parameters.start_date - parameters.timestep,
    )

    if len(energy_forecast) > 0:
        energy_level = energy_forecast.get_value(parameters.start_date - parameters.timestep)
    else:
        energy_level = obj.initial_level.get_value(parameters.start_date - parameters.timestep)

    x_min = filter(lambda x: int(x) <= energy_level, obj.storage_marginal_value.index)
    x_max = filter(lambda x: int(x) > energy_level, obj.storage_marginal_value.index)

    if x_min:
        xp_min = max(x_min, key=lambda x: int(x))
        level_inf = obj.storage_marginal_value.select(xp_min)
    if x_max:
        xp_max = min(x_max, key=lambda x: int(x))
        level_sup = obj.storage_marginal_value.select(xp_max)
    if x_min and x_max:
        weight_inf = (int(xp_max) - energy_level) / (int(xp_max) - int(xp_min))
        weight_sup = (energy_level - int(xp_min)) / (int(xp_max) - int(xp_min))

    # Now we loop over the time stamps for which we want an offer to be made.
    # We formulate as many offers as there are time stamps in orders_time.

    # Compute the actual volumes of fragments, according to maximum_power
    capacity = obj.maximum_power[time]
    volumes = {key: capacity * vu[0] for key, vu in delta_wu.items()}

    if time in parameters.hydraulic_op_times:
        obj.power_level_fragment_sum[time] = 0

        # create an offer for each element in volumes
        for k, v in volumes.items():
            if not x_min and x_max:
                price = level_sup.get_value(time) + delta_wu[k][1]
            elif not x_max and x_min:
                price = level_inf.get_value(time) + delta_wu[k][1]
            elif not x_max and not x_min:
                price = delta_wu[k][1]
            else:
                # This AREA DEAL WITH THE PRICE
                p_min = level_inf.get_value(time)
                p_max = level_sup.get_value(time)
                price = weight_inf * p_min + weight_sup * p_max + delta_wu[k][1]

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_frag_{k}_at_{str(time)}",
                lower_bound=0,
                upper_bound=v,
            )
            obj.price_fragment[k][time] = price

            if k == 0:
                obj.power_level_fragment_sum[time] = obj.power_level_fragment[k][time]
            else:
                obj.power_level_fragment_sum[time] += obj.power_level_fragment[k][time]
