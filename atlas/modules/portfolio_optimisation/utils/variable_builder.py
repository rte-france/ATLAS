from pendulum import DateTime

from atlas.enum import StorageType
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.wind import Wind
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.get_fragment_price import get_fragment_price_and_size
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

        for _, time in enumerate(parameters.hydraulic_op_times):
            min_power = obj.minimum_power.get_value(time)
            max_power = obj.maximum_power.get_value(time)
            max_energy = obj.maximum_energy.get_value(time)

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"{obj.name}_stored_energy_{time}",
                lower_bound=0,
                upper_bound=max_energy,
            )
            get_fragment_price_and_size(obj, time, parameters, model)

            maximum_automated = obj.maximum_afrr + obj.maximum_fcr

            # Optimisation Variables related to reserves
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
                name=f"relaxed_reservese_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=0,
            )
            model.add_continuous_variable(
                name=f"automated_res_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"automated_res_down_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"contracted_diff_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"contracted_diff_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_contracted_diff_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_contracted_diff_down_e_{obj.name}_at_{time}",
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
        for _, time in enumerate(parameters.target_times):
            max_power = obj.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)

            min_power = (1 - obj.maximum_curtailment_ratio.get_value(time)) * max_power

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )

            maximum_automated = obj.maximum_afrr + obj.maximum_fcr

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
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"contracted_diff_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"contracted_diff_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_contracted_diff_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_contracted_diff_down_e_{obj.name}_at_{time}",
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
        for _, time in enumerate(op_time_frame):
            max_power = obj.maximum_power.get_value(time)
            if obj.minimum_power or len(obj.minimum_power) == 0:
                min_power = -max_power
            else:
                min_power = obj.minimum_power.get_value(time)

            maximum_energy = obj.maximum_energy.get_value(time)
            min_state_of_charge = obj.minimum_state_of_charge.get_value(time)

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_sell_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_buy_{time}",
                lower_bound=min_power,
                upper_bound=0,
            )

            model.add_boolean_variable(
                name=f"{obj.name}_is_sell_{time}",
            )

            model.add_continuous_variable(
                name=f"{obj.name}_stored_energy_{time}",
                lower_bound=min_state_of_charge * maximum_energy,
                upper_bound=maximum_energy,
            )

            maximum_automated = obj.maximum_afrr + obj.maximum_fcr

            nbr_fragment = MAPPING_STORAGE_TYPE_OPTIMISATION_TIMES[obj.storage_type]["fragment"]

            for n in range(0, nbr_fragment):
                model.add_continuous_variable(
                    name=f"{obj.name}_power_level_sell_n_{n}_time_{time}",
                    lower_bound=0,
                    upper_bound=max_power,
                )
                model.add_continuous_variable(
                    name=f"{obj.name}_power_level_buy_n_{n}_time_{time}",
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
        for _, time in enumerate(parameters.target_times):
            max_power = obj.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)

            model.add_continuous_variable(
                f"{obj.name}_power_level_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
