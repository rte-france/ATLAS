from pendulum import DateTime

from atlas.enum import LoadType
from atlas.models.equipment.load import Load
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_power, get_minimum_power, get_price
from atlas.solver.solver_interface import OptimisationModel


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
        if time in parameters.target_times:
            power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")
            if obj.load_type == LoadType.POWER_TO_GAS:
                model.add_objective((get_price(obj, time) - price_forecast) * power_level_var * parameters.timestep)
            else:
                model.add_objective(get_price(obj, time) * -power_level_var * parameters.timestep)

            model.add_constraint(power_level_var >= get_maximum_power(obj, time))
            model.add_constraint(power_level_var <= get_minimum_power(obj, time))
