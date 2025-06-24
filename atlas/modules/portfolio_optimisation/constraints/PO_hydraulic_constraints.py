from pendulum import DateTime

from atlas.models.equipment.hydro import Hydro
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


def get_variables_and_constraints_hydraulics(
    time: DateTime,
    hydro_equipments: list[Hydro],
    model: OptimisationModel,
    sum_power_level,
    reserve_up_ti,
    reserve_down_ti,
    automated_reserve_up_ti,
    automated_reserve_down_ti,
    price_forecast,
    parameters: PortfolioOptimisationParameters,
):
    """
    This function formulates the hydraulic reservoir offers.

    Arguments:
    - time: current time step
    - hydro_equipments: dictionary of hydraulic equipment
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

    for obj in hydro_equipments:
        # Check if those optimization variables are useful
        # contracted_difference
        reserve_up_ti.add(obj.reserves_up[time])
        reserve_down_ti.add(obj.reserves_down[time])
        # automated_contracted_difference
        automated_reserve_up_ti.add(obj.automated_reserves_up[time])
        automated_reserve_down_ti.add(obj.automated_reserves_down[time])

        # --- Objective function
        for k in range(0, len(obj.power_level_fragment.keys())):
            if time in parameters.target_times:
                # Create an offer for each element in volumes
                # Add objective function for the specific fragment
                model.add_objective(
                    obj.price_fragment[k][time] * obj.power_level_fragment[k][time] * parameters.timestep
                )
                sum_power_level.add(obj.power_level_fragment[k][time])

            else:
                model.add_objective(
                    -(price_forecast[time] - obj.price_fragment[k][time])
                    * obj.power_level_fragment[k][time]
                    * parameters.timestep
                )

                # FC: Is the following part necessary?
                sum_power_level.add(obj.power_level_fragment[k][time])

        # --- Reserves constraints

        # relaxed_reserve disabling condition (eq. (43))
        if time in parameters.hydraulic_op_times:
            model.add_constraint(obj.relaxed_reserves[time] <= obj.minimum_power[time])

            # Impossible commitment and stable reserves constraints (eq. (44))
            model.add_constraint(obj.automated_reserves_up[time] <= obj.maximum_automated)
            model.add_constraint(obj.automated_reserves_down[time] <= obj.maximum_automated)
            model.add_constraint(obj.reserves_up[time] <= obj.maximum_power[time])
            model.add_constraint(obj.reserves_down[time] <= obj.maximum_power[time])

        # --- Reservoir constraints

        # It would be much clearer if there were no indexes but simply time series.
        if time == parameters.start_date:
            model.add_constraint(
                obj.stored_energy[time]
                == obj.initial_level.get_value(parameters.start_date.add_minutes(-parameters.timestep))
                - obj.power_level_fragment_sum[time] * parameters.timestep
            )

        elif time in parameters.target_times:
            model.add_constraint(
                obj.stored_energy[time]
                == obj.stored_energy[time - parameters.timestep]
                - obj.power_level_fragment_sum[time] * parameters.timestep
            )

        # For any time steps:
        # Respect of minimum and maximum stock constraints
        if time in parameters.target_times:
            reserve_stored_energy_up_ti = obj.automated_reserves_up[time] + obj.reserves_up[time]
            reserve_stored_energy_down_ti = obj.automated_reserves_down[time] + obj.reserves_down[time]

            model.add_constraint(obj.stored_energy[time] >= obj.minimum_energy[time] + reserve_stored_energy_up_ti)
            model.add_constraint(obj.stored_energy[time] <= obj.maximum_energy[time] - reserve_stored_energy_down_ti)
