from pendulum import DateTime

from atlas.models.equipment.hydro import Hydro
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.get_fragment_price import (
    _get_fragment_data,
    _get_fragment_length,
    compute_fragment_prices,
)
from atlas.modules.portfolio_optimisation.utils.getters import (
    get_maximum_automated,
    get_maximum_energy,
    get_maximum_power,
    get_minimum_energy,
    get_minimum_power,
)
from atlas.solver.solver_interface import OptimisationModel


def add_constraints_hydro(
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
            max_power = get_maximum_power(obj, time)
            min_power = get_minimum_power(obj, time)

            model.add_constraint(obj.relaxed_reserves[time] <= min_power)
            model.add_constraint(obj.automated_reserves_up[time] <= get_maximum_automated(obj))
            model.add_constraint(obj.automated_reserves_down[time] <= get_maximum_automated(obj))
            model.add_constraint(obj.reserves_up[time] <= max_power)
            model.add_constraint(obj.reserves_down[time] <= max_power)

        # --- Reservoir constraints
        stored_energy_var = model.get_variable(f"{obj.name}_stored_energy_{time}")
        previous_stored_energy_var = model.get_variable(f"{obj.name}_stored_energy_{time - parameters.timestep}")

        power_level_fragment_sum_var = sum(
            model.get_variable(f"{obj.name}_power_level_frag_{category}_at_{time}")
            for category in _get_fragment_data(obj)
        )

        if time == parameters.start_date:
            model.add_constraint(
                stored_energy_var
                == obj.initial_level.get_value(parameters.start_date - parameters.timestep)
                - power_level_fragment_sum_var * parameters.timestep
            )

        elif time in parameters.target_times:
            model.add_constraint(
                stored_energy_var == previous_stored_energy_var - power_level_fragment_sum_var * parameters.timestep
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
            model.add_constraint(stored_energy_var <= get_maximum_energy(obj, time) - reserve_stored_energy_down_var)
