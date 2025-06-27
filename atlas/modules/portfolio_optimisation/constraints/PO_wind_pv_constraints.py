from pendulum import DateTime

from atlas.models.equipment.solar import Solar
from atlas.models.equipment.wind import Wind
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import (
    get_maximum_automated,
    get_maximum_power,
    get_minimum_power,
    get_price,
)
from atlas.solver.solver_interface import OptimisationModel


def get_variables_and_constraints_wind_pv(
    time: DateTime,
    equipments: list[Wind | Solar],
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
):
    """
    This function formulates the wind and photovoltaic equipments orders.
    """

    for obj in equipments:
        if time in parameters.target_times:
            # Check if those optimization variables are useful

            max_power = get_maximum_power(obj, time)
            min_power = get_minimum_power(obj, time)

            power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")
            automated_reserves_up_var = model.get_variable(f"automated_res_up_e_{obj.name}_{time}")
            automated_reserves_down_var = model.get_variable(f"automated_res_down_e_{obj.name}_{time}")
            reserves_up_var = model.get_variable(f"reserves_up_e_{obj.name}_{time}")
            reserves_down_var = model.get_variable(f"reserves_down_e_{obj.name}_{time}")

            model.add_objective(get_price(obj, time) * power_level_var * parameters.timestep)

            model.add_constraint(power_level_var <= max_power)
            model.add_constraint(power_level_var >= min_power)
            model.add_constraint(automated_reserves_up_var <= get_maximum_automated(obj))
            model.add_constraint(automated_reserves_down_var <= get_maximum_automated(obj))
            model.add_constraint(reserves_up_var <= max_power)
            model.add_constraint(reserves_down_var <= max_power)
