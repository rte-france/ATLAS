from pendulum import DateTime

from atlas.models.equipment.load import Load
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_power, get_minimum_power
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
        power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")
        model.add_constraint(power_level_var >= get_maximum_power(obj, time))
        model.add_constraint(power_level_var <= get_minimum_power(obj, time))
