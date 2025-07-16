from __future__ import annotations

from pendulum import DateTime

from atlas.models.equipment.hydro import Hydro
from atlas.modules.portfolio_optimisation.optimisation.variable_builder import add_reserve_variables
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


class HydroPO(Hydro):
    pass

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        """Build variables for hydro equipment."""
        for time in parameters.hydraulic_op_times:
            min_power = get_minimum_power(self, time)
            max_power = get_maximum_power(self, time)
            max_energy = get_maximum_energy(self, time)
            maximum_automated = get_maximum_automated(self)

            # Basic variables
            model.add_continuous_variable(
                name=f"{self.name}_stored_energy_{time}",
                lower_bound=0,
                upper_bound=max_energy,
            )

            self.add_variable_fragment(model=model, obj=self, time=time, parameters=self.parameters)

            add_reserve_variables(
                model,
                self.name,
                time,
                min_power,
                max_power,
                maximum_automated,
                relaxed_reserves=True,
                storage_equipment=False,
                thermal_equipment=False,
            )

    def add_variable_fragment(
        self,
        model: OptimisationModel,
        obj: HydroPO,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> tuple[dict, dict]:
        """Formulates hydraulic reservoir offers by calculating fragment prices and volumes."""

        fragment_data = _get_fragment_data(obj)

        if time not in parameters.hydraulic_op_times:
            return

        for category, fragment in fragment_data.items():
            volume = get_maximum_power(obj, time) * fragment.volume

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_frag_{category}_at_{time}",
                lower_bound=0,
                upper_bound=volume,
            )

    def add_constraints(
        self,
        time: DateTime,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        This function formulates the hydraulic reservoir offers.
        """

        max_power = get_maximum_power(self, time)
        min_power = get_minimum_power(self, time)

        model.add_constraint(model.get_variable(f"relaxed_reserves_{self.name}_{time}") <= min_power)
        model.add_constraint(
            model.get_variable(f"automated_reserves_up_{self.name}_{time}") <= get_maximum_automated(self)
        )
        model.add_constraint(
            model.get_variable(f"automated_reserves_up_{self.name}_{time}") <= get_maximum_automated(self)
        )
        model.add_constraint(model.get_variable(f"reserves_up_{self.name}_{time}") <= max_power)
        model.add_constraint(model.get_variable(f"reserves_up_{self.name}_{time}") <= max_power)

        # --- Reservoir constraints
        stored_energy_var = model.get_variable(f"{self.name}_stored_energy_{time}")
        previous_stored_energy_var = model.get_variable(f"{self.name}_stored_energy_{time - parameters.timestep}")

        power_level_fragment_sum_var = sum(
            model.get_variable(f"{self.name}_power_level_frag_{category}_at_{time}")
            for category in _get_fragment_data(self)
        )

        if time == parameters.start_date:
            model.add_constraint(
                stored_energy_var
                == self.initial_level.get_value(parameters.start_date - parameters.timestep)
                - power_level_fragment_sum_var * parameters.timestep
            )

        elif time in parameters.target_times:
            model.add_constraint(
                stored_energy_var == previous_stored_energy_var - power_level_fragment_sum_var * parameters.timestep
            )

        # For any time steps:
        # Respect of minimum and maximum stock constraints
        if time in parameters.target_times:
            reserve_stored_energy_up_var = model.get_variable(f"reserves_up_e_{self.name}_{time}") + model.get_variable(
                f"automated_res_up_e_{self.name}_{time}"
            )
            reserve_stored_energy_down_var = model.get_variable(
                f"reserves_down_e_{self.name}_{time}"
            ) + model.get_variable(f"automated_res_down_e_{self.name}_{time}")

            model.add_constraint(stored_energy_var >= get_minimum_energy(self, time) + reserve_stored_energy_up_var)
            model.add_constraint(stored_energy_var <= get_maximum_energy(self, time) - reserve_stored_energy_down_var)

    def add_objective(
        self,
        model: OptimisationModel,
        time: DateTime,
        price_forecast: float,
        parameters: PortfolioOptimisationParameters,
    ):
        for k in range(_get_fragment_length(self)):
            if time in self.parameters.target_times:
                model.add_objective(
                    compute_fragment_prices(self, time, k, parameters)
                    * model.get_variable(f"{self.name}_power_level_frag_{k}_at_{time}")
                    * self.parameters.timestep
                )

            else:
                model.add_objective(
                    -(price_forecast - compute_fragment_prices(self, time, k, parameters))
                    * model.get_variable(f"{self.name}_power_level_frag_{k}_at_{time}")
                    * self.parameters.timestep
                )
