from pendulum import DateTime

from atlas.models.equipment.hydro import Hydro
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.get_fragment_price import _get_fragment_length, compute_fragment_prices
from atlas.modules.portfolio_optimisation.utils.getters import (
    get_maximum_automated,
    get_maximum_energy,
    get_minimum_energy,
)
from atlas.solver.solver_interface import OptimisationModel


def get_variables_and_constraints_hydraulics(
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
        for k in range(_get_fragment_length(obj)):
            if time in parameters.target_times:
                model.add_objective(
                    compute_fragment_prices(obj, time, k, parameters)
                    * model.get_variable(f"{obj.name}_power_level_frag_{k}_at_{time}")
                    * parameters.timestep
                )

            else:
                model.add_objective(
                    -(price_forecast - compute_fragment_prices(obj, time, k, parameters))
                    * model.get_variable(f"{obj.name}_power_level_frag_{k}_at_{time}")
                    * parameters.timestep
                )

        # relaxed_reserve disabling condition (eq. (43))
        if time in parameters.hydraulic_op_times:
            model.add_constraint(obj.relaxed_reserves[time] <= obj.minimum_power[time])

            # Impossible commitment and stable reserves constraints (eq. (44))
            model.add_constraint(obj.automated_reserves_up[time] <= get_maximum_automated(obj))
            model.add_constraint(obj.automated_reserves_down[time] <= get_maximum_automated(obj))
            model.add_constraint(obj.reserves_up[time] <= obj.maximum_power[time])
            model.add_constraint(obj.reserves_down[time] <= obj.maximum_power[time])

        # --- Reservoir constraints
        stored_energy_var = model.get_variable(f"{obj.name}_stored_energy_{time}")
        # It would be much clearer if there were no indexes but simply time series.
        if time == parameters.start_date:
            model.add_constraint(
                stored_energy_var
                == obj.initial_level.get_value(parameters.start_date - parameters.timestep)
                - obj.power_level_fragment_sum[time] * parameters.timestep
            )

        elif time in parameters.target_times:
            model.add_constraint(
                stored_energy_var
                == obj.stored_energy[time - parameters.timestep]
                - obj.power_level_fragment_sum[time] * parameters.timestep
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
            model.add_constraint(stored_energy_var <= get_maximum_energy(time) - reserve_stored_energy_down_var)
