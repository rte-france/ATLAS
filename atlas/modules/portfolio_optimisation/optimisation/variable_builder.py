from typing import cast

from pendulum import DateTime

from atlas.models.equipment.equipment import Equipment
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.models.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.models.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class VariableBuilder:
    """Builds all optimization variables for the portfolio optimization model."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def build_variables(
        self,
        model: OptimisationModel,
        portfolio: PortfolioPO,
    ):
        """Build all variables for the optimization model."""

        self._build_equipment_variables(model, portfolio.equipments)
        portfolio.add_variables(model, self.parameters.target_times, self.parameters)

    def _build_equipment_variables(
        self,
        model: OptimisationModel,
        equipments: dict[str, list[type[Equipment]]],
    ):
        """Build variables for all equipment types."""
        for equipment_type in equipments:
            for obj in cast(
                list[HydroPO | LoadPO | WindPO | StoragePO | ThermalPO | OtherNonDispatchablePO],
                equipments.get(equipment_type, []),
            ):
                obj.add_variables(model, self.parameters)

    # def _build_thermal_variables(self, model: OptimisationModel, equipments: list[Thermal]):
    #     for obj in equipments:
    #         timing_params = self._calculate_thermal_timing_params(obj)

    #         optimisation_times, stable_optimisation_times = self._get_thermal_optimization_times(obj, timing_params)

    #         if timing_params["T_stable"] >= 1:
    #             model.add_boolean_variable(
    #                 name=f"ON_UP_var_e_{obj.name}_at_{self.parameters.start_date - self.parameters.timestep}"
    #             )
    #             model.add_boolean_variable(
    #                 name=f"ON_DOWN_var_e_{obj.name}_at_{self.parameters.start_date - self.parameters.timestep}"
    #             )

    #         for time in stable_optimisation_times:
    #             min_power = get_minimum_power(obj, time)
    #             max_power = get_maximum_power(obj, time)
    #             maximum_automated = obj.maximum_afrr + obj.maximum_fcr

    #             if timing_params["T_stable"] >= 1:
    #                 model.add_boolean_variable(name=f"ON_FLAT_e_{obj.name}_at_{time}")
    #                 model.add_boolean_variable(name=f"stable_at_{time}_e_{obj.name}")
    #                 model.add_boolean_variable(name=f"entered_up_at_{time}_e_{obj.name}")
    #                 model.add_boolean_variable(name=f"entered_down_at_{time}_e_{obj.name}")

    #             # Power level variables (only for thermal_op_times)
    #             if time in self.parameters.thermal_op_times:
    #                 model.add_continuous_variable(
    #                     name=f"{obj.name}_p_lev_{time}",
    #                     lower_bound=0,
    #                     upper_bound=max_power,
    #                 )
    #                 model.add_continuous_variable(
    #                     name=f"{obj.name}_p_lev_above_maxAvail_{time}",
    #                     lower_bound=0,
    #                     upper_bound=max_power,
    #                 )
    #                 model.add_continuous_variable(
    #                     name=f"{obj.name}_p_lev_below_minAvail_{time}",
    #                     lower_bound=0,
    #                     upper_bound=max_power,
    #                 )

    #             if time in optimisation_times:
    #                 model.add_boolean_variable(name=f"OFF_var_e_{obj.name}_at_{time}")
    #                 model.add_boolean_variable(name=f"ON_UP_var_e_{obj.name}_at_{time}")
    #                 model.add_boolean_variable(name=f"ON_DOWN_var_e_{obj.name}_at_{time}")
    #                 model.add_boolean_variable(name=f"t_on_of_e_{obj.name}_at_{time}")
    #                 model.add_boolean_variable(name=f"t_off_of_e_{obj.name}_at_{time}")

    #                 if timing_params["T_start"] >= 1:
    #                     model.add_boolean_variable(name=f"ON_START_e_{obj.name}_at_{time}")

    #                 if timing_params["T_stop"] >= 1:
    #                     model.add_boolean_variable(name=f"STOP_e_{obj.name}_at_{time}")

    #                 model.add_continuous_variable(
    #                     name=f"UP_grad_at_{time}_for_e_{obj.name}",
    #                     lower_bound=-inf,
    #                     upper_bound=inf,
    #                 )
    #                 model.add_continuous_variable(
    #                     name=f"aux_up_grad_at_{time}_e_{obj.name}",
    #                     lower_bound=-inf,
    #                     upper_bound=inf,
    #                 )
    #                 model.add_continuous_variable(
    #                     name=f"DOWN_grad_at_{time}_e_{obj.name}",
    #                     lower_bound=-inf,
    #                     upper_bound=inf,
    #                 )
    #                 model.add_continuous_variable(
    #                     name=f"aux_down_grad_at_{time}_e_{obj.name}",
    #                     lower_bound=-inf,
    #                     upper_bound=inf,
    #                 )

    #                 # Additional conditional variables
    #                 if (
    #                     timing_params["T_stop"] >= 1
    #                     and timing_params["T_start"] == 0
    #                     and timing_params["T_stable"] == 0
    #                 ):
    #                     model.add_boolean_variable(name=f"down_to_stop_grad_at_{time}_e_{obj.name}")

    #                 if timing_params["T_stop"] >= 1 and timing_params["T_stable"] >= 1:
    #                     model.add_boolean_variable(name=f"flat_down_stop_at_{time}_e_{obj.name}")

    #                 if timing_params["T_stable"] >= 1 and (
    #                     timing_params["T_start"] >= 1 or timing_params["T_stop"] >= 1
    #                 ):
    #                     model.add_continuous_variable(
    #                         name=f"DD_grad_at_{time}_e_{obj.name}",
    #                         lower_bound=-inf,
    #                         upper_bound=inf,
    #                     )

    #                 if (
    #                     timing_params["T_stop"] >= 1
    #                     and timing_params["T_start"] >= 1
    #                     and timing_params["T_stable"] == 0
    #                 ):
    #                     model.add_boolean_variable(name=f"down_to_stop_grad_at_{time}_e_{obj.name}")

    #                 # Handle special case for T_stable >= 1: add extra time step variables
    #                 if timing_params["T_stable"] >= 1:
    #                     # Add variables for start_date - 1 time step
    #                     startDate_minus_one_enum = -1  # or use appropriate indexing
    #                     model.add_boolean_variable(name=f"ON_UP_var_e_{obj.name}_at_{startDate_minus_one_enum}")
    #                     model.add_boolean_variable(name=f"ON_DOWN_var_e_{obj.name}_at_{startDate_minus_one_enum}")

    #                 # Handle special case for DD variables: add time step before start_date
    #                 if timing_params["T_stable"] >= 1 and (
    #                     timing_params["T_start"] >= 1 or timing_params["T_stop"] >= 1
    #                 ):
    #                     model.add_continuous_variable(
    #                         name=f"DD_grad_at_{-1}_e_{obj.name}",
    #                         lower_bound=-inf,
    #                         upper_bound=inf,
    #                     )

    #                     # Reserve variables
    #                     self._add_reserve_variables(
    #                         model,
    #                         obj.name,
    #                         time,
    #                         min_power,
    #                         max_power,
    #                         maximum_automated,
    #                         relaxed_reserves=True,
    #                         storage_equipment=False,
    #                         thermal_equipment=True,
    #                     )

    # def _calculate_thermal_timing_params(self, obj: Thermal) -> dict:
    #     """Calculate timing parameters for thermal equipment."""
    #     # Convert time constraints to time steps

    #     # Calculate T_on
    #     if obj.minimum_time_on != 0:
    #         T_on = int(max(1, math.ceil(obj.minimum_time_on * 60.0 / self.parameters.timestep))) + 1
    #     else:
    #         T_on = 0

    #     # Calculate T_off
    #     if obj.minimum_time_off != 0:
    #         T_off = int(max(1, math.ceil(obj.minimum_time_off * 60.0 / self.parameters.timestep))) + 1
    #     else:
    #         T_off = 0

    #     # Calculate other timing parameters
    #     T_start = int(math.floor(obj.startup_duration * 60.0 / self.parameters.timestep))
    #     T_stop = int(math.floor(obj.shutdown_duration * 60.0 / self.parameters.timestep))

    #     # Calculate T_stable
    #     if obj.minimum_stable_power_duration * 60.0 < self.parameters.timestep:
    #         T_stable = 0
    #     else:
    #         T_stable = int(math.ceil(obj.minimum_stable_power_duration * 60.0 / self.parameters.timestep)) + 1

    #     # Rescale T_stable so that it is either equal to 0 or >= 2
    #     T_stable = T_stable if T_stable >= 2 else 0

    #     # Calculate T_traceback
    #     T_traceback = int(max(T_on + T_start, T_off + T_stop))

    #     return {
    #         "T_on": T_on,
    #         "T_off": T_off,
    #         "T_start": T_start,
    #         "T_stop": T_stop,
    #         "T_stable": T_stable,
    #         "T_traceback": T_traceback,
    #     }

    # def _get_thermal_optimization_times(self, obj: Thermal, timing_params: dict) -> list[DateTime]:
    #     """Get the optimization time frame for thermal equipment."""
    #     # Create extended time frame similar to the legacy code
    #     T_traceback = timing_params["T_traceback"]

    #     optimisation_times = generate_datetimes(
    #         self.parameters.start_date,
    #         self.parameters.thermal_optimization_period + T_traceback,
    #         self.parameters.timestep,
    #     )

    #     stable_optimisation_times = generate_datetimes(
    #         self.parameters.start_date - self.parameters.timestep,
    #         self.parameters.thermal_optimization_period + T_traceback,
    #         self.parameters.timestep,
    #     )

    #     return optimisation_times, stable_optimisation_times


def add_reserve_variables(
    model: OptimisationModel,
    name: str,
    time: DateTime,
    min_power: float,
    max_power: float,
    maximum_automated: float,
    relaxed_reserves: bool,
    storage_equipment: bool,
    thermal_equipment: bool,
):
    """Add reserve variables for solar/wind equipment"""
    model.add_continuous_variable(
        name=f"reserves_up_{name}_{time}",
        lower_bound=0,
        upper_bound=max_power,
    )
    model.add_continuous_variable(
        name=f"reserves_down_{name}_{time}",
        lower_bound=min_power if not thermal_equipment else 0,
        upper_bound=max_power,
    )
    model.add_continuous_variable(
        name=f"unprovided_reserves_up_{name}_{time}",
        lower_bound=0,
        upper_bound=max_power,
    )
    model.add_continuous_variable(
        name=f"unprovided_reserves_down_{name}_{time}",
        lower_bound=min_power if not thermal_equipment else 0,
        upper_bound=max_power,
    )
    model.add_continuous_variable(
        name=f"automated_reserves_up_{name}_{time}",
        lower_bound=0,
        upper_bound=maximum_automated,
    )
    if not storage_equipment:
        model.add_continuous_variable(
            name=f"automated_reserves_down_{name}_{time}",
            lower_bound=0,
            upper_bound=maximum_automated,
        )
    else:
        model.add_continuous_variable(
            name=f"automated_reserves_down_{name}_{time}",
            lower_bound=-maximum_automated,
            upper_bound=maximum_automated,
        )
    if not storage_equipment and not thermal_equipment:
        model.add_continuous_variable(
            name=f"contracted_diff_up_{name}_{time}",
            lower_bound=0,
            upper_bound=max_power,
        )
        model.add_continuous_variable(
            name=f"contracted_diff_down_{name}_{time}",
            lower_bound=min_power,
            upper_bound=max_power,
        )
        model.add_continuous_variable(
            name=f"automated_contracted_diff_up_{name}_{time}",
            lower_bound=0,
            upper_bound=max_power,
        )
        model.add_continuous_variable(
            name=f"automated_contracted_diff_down_{name}_{time}",
            lower_bound=min_power,
            upper_bound=max_power,
        )

    if relaxed_reserves:
        model.add_continuous_variable(
            name=f"relaxed_reserves_{name}_{time}",
            lower_bound=min_power if not thermal_equipment else 0,
            upper_bound=0 if not thermal_equipment else min_power,
        )
