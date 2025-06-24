from ast import Load

from pendulum import DateTime

from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


def get_variables_and_constraints_load(
    time: DateTime,
    load_equipments: list[Load],
    model: OptimisationModel,
    sum_power_level,
    price_forecast,
    parameters: PortfolioOptimisationParameters,
):
    """
    This function adds constraints and elements in the objective function related to load equipments.

    Arguments:
    - time: current time step
    - load_equipments: dictionary of load equipments
    - obj_function: objective function to optimize
    - constraint_list: list of constraints
    - sum_power_level: sum of power levels
    - reserve_up_ti: upward reserves at time t
    - reserve_down_ti: downward reserves at time t
    - automated_reserve_up_ti: automated upward reserves at time t
    - automated_reserve_down_ti: automated downward reserves at time t
    - price_forecast: price forecast data
    - parameters: parameters object
    """

    for obj in load_equipments:
        if time in parameters.target_times:
            max_power_ti = obj.maximum_power[time]
            min_power_ti = obj.minimum_power[time]

            if obj.load_type == "power_to_gas":
                # Objective function
                model.add_objective(
                    (obj.price[time] - price_forecast[time]) * obj.power_level[time] * parameters.timestep / 60.0
                )
            else:
                # Objective function
                model.add_objective(obj.price[time] * -obj.power_level[time] * parameters.timestep / 60.0)

            # Maximum and Minimum Power (opposite direction compared to generation units)
            model.add_constraint(obj.power_level[time] >= max_power_ti)
            model.add_constraint(obj.power_level[time] <= min_power_ti)

            sum_power_level.add(obj.power_level[time])
