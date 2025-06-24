from pendulum import DateTime

from atlas.models.equipment.solar import Solar
from atlas.models.equipment.wind import Wind
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


def get_variables_and_constraints_wind_pv(
    time: DateTime,
    equipments: list[Wind | Solar],
    model: OptimisationModel,
    sum_power_level,
    reserve_up_ti,
    reserve_down_ti,
    automated_reserve_up_ti,
    automated_reserve_down_ti,
    parameters: PortfolioOptimisationParameters,
):
    """
    This function formulates the wind and photovoltaic equipments orders.

    Arguments:
    - time: current time step
    - equipments: dictionary of wind or photovoltaic equipments
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

    for obj in equipments:
        if time in parameters.target_times:
            # Check if those optimization variables are useful

            reserve_up_ti.add(obj.reserves_up[time])
            reserve_down_ti.add(obj.reserves_down[time])
            # automated_contracted_difference
            automated_reserve_up_ti.add(obj.automated_reserves_up[time])
            automated_reserve_down_ti.add(obj.automated_reserves_down[time])

            max_power_ti = obj.maximum_power[time]
            min_power_ti = obj.minimum_power[time]

            # Objective function
            model.add_objective(obj.price[time] * obj.power_level[time] * parameters.timestep)

            # Maximum and Minimum Power
            model.add_constraint(obj.power_level[time] <= max_power_ti)
            model.add_constraint(obj.power_level[time] >= min_power_ti)

            # relaxed_reserve disabling condition (eq. (43))
            # model.add_constraint(obj.relaxed_reserves[time] <= min_power_ti)

            # Impossible commitment and stable reserves constraints (eq. (44))
            model.add_constraint(obj.automated_reserves_up[time] <= obj.maximum_automated)
            model.add_constraint(obj.automated_reserves_down[time] <= obj.maximum_automated)
            model.add_constraint(obj.reserves_up[time] <= max_power_ti)
            model.add_constraint(obj.reserves_down[time] <= max_power_ti)

            sum_power_level.add(obj.power_level[time])
