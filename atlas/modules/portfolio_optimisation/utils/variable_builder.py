from pendulum import DateTime

from atlas.enum import StorageType
from atlas.models.equipment.equipment import Equipment
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.wind import Wind
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.parameters import MarketEnum, PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.get_fragment_price import get_fragment_price_and_size
from atlas.modules.portfolio_optimisation.utils.getters import (
    get_maximum_automated,
    get_maximum_energy,
    get_maximum_power,
    get_minimum_power,
    get_reserve,
)
from atlas.solver.solver_interface import OptimisationModel


def add_variables_hydro(
    time: DateTime,
    equipments: list[Hydro],
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
):
    for obj in equipments:
        for _, time in enumerate(parameters.hydraulic_op_times):
            min_power = get_minimum_power(obj, time)
            max_power = get_maximum_power(obj, time)
            max_energy = get_maximum_energy(obj, time)

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

            maximum_automated = get_maximum_automated(obj)

            # Optimisation Variables related to reserves
            model.add_continuous_variable(
                name=f"reserves_up_e_{obj.name}_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"reserves_down_e_{obj.name}_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"unprovided_reserves_up_e_{obj.name}_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"unprovided_reserves_down_e_{obj.name}_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"relaxed_reserves_{obj.name}_{time}",
                lower_bound=min_power,
                upper_bound=0,
            )
            model.add_continuous_variable(
                name=f"automated_res_up_e_{obj.name}_{time}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"automated_res_down_e_{obj.name}_{time}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"contracted_diff_up_e_{obj.name}_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"contracted_diff_down_e_{obj.name}_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_contracted_diff_up_e_{obj.name}_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_contracted_diff_down_e_{obj.name}_{time}",
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
        for time in parameters.target_times:
            max_power = get_maximum_power(obj, time)
            min_power = get_minimum_power(obj, time)
            maximum_automated = obj.maximum_afrr + obj.maximum_fcr

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_{time}",
                lower_bound=0,
                upper_bound=max_power,
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
        op_time_frame = MAPPING_STORAGE_TYPE_OPTIMISATION_TIMES[obj.storage_type]["op_time_frame"]
        for _, time in enumerate(op_time_frame):
            min_power = get_minimum_power(obj, time)
            max_power = get_maximum_power(obj, time)
            maximum_energy = get_maximum_energy(time)
            maximum_automated = obj.maximum_afrr + obj.maximum_fcr
            nbr_fragment = MAPPING_STORAGE_TYPE_OPTIMISATION_TIMES[obj.storage_type]["fragment"]

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
                lower_bound=obj.minimum_state_of_charge.get_value(time) * maximum_energy,
                upper_bound=maximum_energy,
            )

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


def add_variables_portfolio(
    portfolio: Portfolio,
    equipments: dict[str, list[type[Equipment]]],
    times: list[DateTime],
    parameters: PortfolioOptimisationParameters,
    model: OptimisationModel,
):
    """Add optimization variables for portfolio management."""
    sum_maximum_energy = 0

    residual_energy = {}
    reserve_up = {}
    reserve_down = {}
    automated_reserve_up = {}
    automated_reserve_down = {}

    for idx, time in enumerate(times):
        sum_residual_energy = 0
        sum_reserves_up = 0
        sum_reserves_down = 0
        sum_automated_reserves_up = 0
        sum_automated_reserves_down = 0
        sum_maximum_power = 0

        # Process non-dispatchable productions
        sum_residual_energy = _process_non_dispatchable_production(
            equipments["non_dispatchable_production"],
            idx,
            time,
            parameters,
            sum_residual_energy,
        )

        # Process non-dispatchable loads
        sum_residual_energy = _process_non_dispatchable_loads(
            equipments["non_dispatchable_load"],
            idx,
            time,
            parameters,
            sum_residual_energy,
        )

        # Process all equipment types that need reserve calculations
        reserve_data, sum_maximum_energy = _process_equipment_with_reserves(
            equipments,
            idx,
            time,
            parameters,
            sum_residual_energy,
            sum_reserves_up,
            sum_reserves_down,
            sum_automated_reserves_up,
            sum_automated_reserves_down,
            sum_maximum_power,
            sum_maximum_energy,
        )

        sum_residual_energy, sum_reserves_up, sum_reserves_down = reserve_data[:3]
        sum_automated_reserves_up, sum_automated_reserves_down, sum_maximum_power = reserve_data[3:]

        # Store values for current time
        residual_energy[time] = sum_residual_energy
        reserve_up[time] = sum_reserves_up
        reserve_down[time] = sum_reserves_down
        automated_reserve_up[time] = sum_automated_reserves_up
        automated_reserve_down[time] = sum_automated_reserves_down

        _add_optimization_variables(
            portfolio, times, sum_maximum_energy, sum_residual_energy, sum_maximum_power, parameters, model
        )


def _process_non_dispatchable_production(
    equipments: list[OtherNonDispatchable],
    time: DateTime,
    parameters: PortfolioOptimisationParameters,
    sum_residual_energy: float,
) -> float:
    """Process non-dispatchable production equipment."""
    for obj in equipments:
        last_forecast_ti = obj.maximum_power_forecast.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_date
        ).get_value(time)

        upstream_sold_energy = _get_upstream_energy(obj, time, parameters)
        optimal_dispatch = min(last_forecast_ti, upstream_sold_energy)
        sum_residual_energy += upstream_sold_energy - optimal_dispatch

    return sum_residual_energy


def _process_non_dispatchable_loads(
    equipments: list[Load],
    time: DateTime,
    parameters: PortfolioOptimisationParameters,
    sum_residual_energy: float,
) -> float:
    """Process non-dispatchable load equipment."""
    for obj in equipments:
        last_forecast_ti = obj.maximum_power_forecast.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_date
        ).get_value(time)

        upstream_bought_energy = _get_upstream_energy(obj, time, parameters)
        optimal_dispatch = min(last_forecast_ti, upstream_bought_energy)
        sum_residual_energy += upstream_bought_energy - optimal_dispatch

    return sum_residual_energy


def _get_upstream_energy(obj: type[Equipment], time: DateTime, parameters: PortfolioOptimisationParameters) -> float:
    """Get upstream energy (bought or sold) based on market type."""
    if parameters.market == MarketEnum.rr_activation:
        return obj.rr_activated.get_value(time)
    elif parameters.market == MarketEnum.mfrr_activation:
        return obj.mfrr_activated.get_value(time)
    else:
        return obj.total_id_cleared_quantity.get_value(time) + obj.da_cleared_quantity.get_value(time)


def _process_equipment_with_reserves(
    equipments: dict[str, list[type[Equipment]]],
    idx: int,
    time: DateTime,
    parameters: PortfolioOptimisationParameters,
    sum_residual_energy: float,
    sum_reserves_up: float,
    sum_reserves_down: float,
    sum_automated_reserves_up: float,
    sum_automated_reserves_down: float,
    sum_maximum_power: float,
    sum_maximum_energy: float,
) -> tuple:
    """Process equipment types that require reserve calculations."""
    equipment_types = ["dispatchable_load", "wind", "solar", "thermal", "hydro", "storage"]

    for equipment_type in equipment_types:
        for obj in equipments[equipment_type]:
            # Add upstream energy to residual
            upstream_energy = _get_upstream_energy(obj, time, parameters)
            sum_residual_energy += upstream_energy
            sum_maximum_power += get_maximum_power(obj, time, parameters.execution_date)

            (
                sum_reserves_up,
                sum_reserves_down,
                sum_automated_reserves_up,
                sum_automated_reserves_down,
                sum_maximum_power,
            ) = get_reserve(
                obj,
                sum_reserves_up,
                sum_reserves_down,
                sum_automated_reserves_up,
                sum_automated_reserves_down,
                sum_maximum_power,
                time,
                parameters,
            )
            # Update max energy total on first iteration
            if idx == 0:
                sum_maximum_energy += abs(get_maximum_power(obj, time))

    return (
        sum_residual_energy,
        sum_reserves_up,
        sum_reserves_down,
        sum_automated_reserves_up,
        sum_automated_reserves_down,
        sum_maximum_power,
    ), sum_maximum_energy


def _add_optimization_variables(
    portfolio: Portfolio,
    time: DateTime,
    sum_maximum_energy: float,
    sum_residual_enery: dict,
    max_power: dict,
    parameters: PortfolioOptimisationParameters,
    model: OptimisationModel,
):
    """Add optimization variables to the model."""

    small_imbalance_limit = sum_maximum_energy * parameters.small_imbalance_size
    max_overall_imbal = max(sum_residual_enery * parameters.maximum_imbalance)

    # Imbalance variables
    model.add_continuous_variable(
        name=f"{portfolio.name}_small_imbalance_up_{time}",
        lower_bound=0,
        upper_bound=small_imbalance_limit,
    )
    model.add_continuous_variable(
        name=f"{portfolio.name}_large_imbalance_up_{time}",
        lower_bound=0,
        upper_bound=max_overall_imbal,
    )
    model.add_continuous_variable(
        name=f"{portfolio.name}_small_imbalance_down_{time}",
        lower_bound=0,
        upper_bound=small_imbalance_limit,
    )
    model.add_continuous_variable(
        name=f"{portfolio.name}_large_imbalance_down_{time}",
        lower_bound=0,
        upper_bound=max_overall_imbal,
    )

    # Contract difference variables
    contract_vars = [
        "contracted_diff_up",
        "contracted_diff_down",
        "auto_contracted_diff_up",
        "auto_contracted_diff_down",
    ]

    for var_type in contract_vars:
        model.add_continuous_variable(
            name=f"{var_type}_{portfolio.name}_{time}",
            lower_bound=0,
            upper_bound=max_power[time],
        )
