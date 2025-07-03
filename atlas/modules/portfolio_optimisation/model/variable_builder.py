import math
from typing import cast

from pendulum import DateTime

from atlas.models.equipment.equipment import Equipment
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.thermal import Thermal
from atlas.models.equipment.wind import Wind
from atlas.modules.portfolio_optimisation.parameters import MarketEnum, PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.get_fragment_price import _get_fragment_data
from atlas.modules.portfolio_optimisation.utils.getters import (
    get_maximum_automated,
    get_maximum_energy,
    get_maximum_power,
    get_minimum_power,
    get_reserve,
)
from atlas.solver.solver_interface import OptimisationModel


class VariableBuilder:
    """Builds all optimization variables for the portfolio optimization model."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def build_variables(
        self,
        model: OptimisationModel,
        portfolio_name: str,
        equipments: dict[str, list[type[Equipment]]],
    ):
        """Build all variables for the optimization model."""

        self._build_equipment_variables(model, equipments)

        self._build_portfolio_variables(model, portfolio_name, equipments, self.parameters.target_times)

    def _build_equipment_variables(
        self,
        model: OptimisationModel,
        equipments: dict[str, list[type[Equipment]]],
    ):
        """Build variables for all equipment types."""
        if "hydro" in equipments:
            self._build_hydro_variables(model, cast(list[Hydro], equipments["hydro"]))

        if "solar" in equipments:
            self._build_solar_wind_variables(model, cast(list[Solar], equipments["solar"]))

        if "wind" in equipments:
            self._build_solar_wind_variables(model, cast(list[Wind], equipments["wind"]))

        if "storage" in equipments:
            self._build_storage_variables(model, cast(list[Storage], equipments["storage"]))

        if "load" in equipments:
            self._build_load_variables(model, cast(list[Load], equipments["load"]))

        if "thermal" in equipments:
            self._build_thermal_variables(model, cast(list[Thermal], equipments["thermal"]))

    def _build_portfolio_variables(
        self,
        model: OptimisationModel,
        portfolio_name: str,
        equipments: dict[str, list[type[Equipment]]],
        times: list[DateTime],
    ):
        """Build portfolio-level optimization variables."""

        for time in times:
            residual_energy = self._compute_residual_energy(equipments, time)
            maximum_power, maximum_energy = self._compute_power_and_energy(equipments, time)
            self._add_imbalance_variables(model, portfolio_name, time, residual_energy, maximum_energy)
            self._add_contract_difference_variables(model, portfolio_name, time, maximum_power)

    def _build_thermal_variables(self, model: OptimisationModel, equipments: list[Thermal]):
        """Build variables for thermal equipment."""
        for obj in equipments:
            # Calculate timing parameters
            timing_params = self._calculate_thermal_timing_params(obj)

            # Get optimization times for this thermal equipment
            thermal_times = self._get_thermal_optimization_times(obj, timing_params)

            for time in thermal_times:
                min_power = get_minimum_power(obj, time)
                max_power = get_maximum_power(obj, time)
                maximum_automated = obj.maximum_afrr + obj.maximum_fcr

                # Power level variables (only for thermal_op_times)
                if time in self.parameters.thermal_op_times:
                    model.add_continuous_variable(
                        name=f"{obj.name}_power_level_{time}",
                        lower_bound=0,
                        upper_bound=max_power,
                    )
                    model.add_continuous_variable(
                        name=f"{obj.name}_additional_power_{time}",
                        lower_bound=0,
                        upper_bound=max_power,
                    )
                    model.add_continuous_variable(
                        name=f"{obj.name}_additional_power_below_{time}",
                        lower_bound=0,
                        upper_bound=max_power,
                    )

                # State variables - always defined
                model.add_boolean_variable(name=f"{obj.name}_off_{time}")
                model.add_boolean_variable(name=f"{obj.name}_on_up_{time}")
                model.add_boolean_variable(name=f"{obj.name}_on_down_{time}")
                model.add_boolean_variable(name=f"{obj.name}_turned_on_{time}")
                model.add_boolean_variable(name=f"{obj.name}_turned_off_{time}")

                # Conditional state variables based on timing parameters
                if timing_params["T_start"] >= 1:
                    model.add_boolean_variable(name=f"{obj.name}_start_{time}")

                if timing_params["T_stop"] >= 1:
                    model.add_boolean_variable(name=f"{obj.name}_stop_{time}")

                if timing_params["T_stable"] >= 1:
                    model.add_boolean_variable(name=f"{obj.name}_on_flat_{time}")
                    model.add_boolean_variable(name=f"{obj.name}_stable_{time}")
                    model.add_boolean_variable(name=f"{obj.name}_entered_up_{time}")
                    model.add_boolean_variable(name=f"{obj.name}_entered_down_{time}")

                    # Gradient auxiliary variables
                    q_max = max_power
                    q_min = -q_max

                    model.add_continuous_variable(
                        name=f"{obj.name}_u_{time}",
                        lower_bound=q_min,
                        upper_bound=q_max,
                    )
                    model.add_continuous_variable(
                        name=f"{obj.name}_tilde_u_{time}",
                        lower_bound=q_min,
                        upper_bound=q_max,
                    )
                    model.add_continuous_variable(
                        name=f"{obj.name}_d_{time}",
                        lower_bound=q_min,
                        upper_bound=q_max,
                    )
                    model.add_continuous_variable(
                        name=f"{obj.name}_tilde_d_{time}",
                        lower_bound=q_min,
                        upper_bound=q_max,
                    )

                # Additional conditional variables
                if timing_params["T_stop"] >= 1 and timing_params["T_start"] == 0 and timing_params["T_stable"] == 0:
                    model.add_boolean_variable(name=f"{obj.name}_down_to_stop_{time}")

                if timing_params["T_stop"] >= 1 and timing_params["T_stable"] >= 1:
                    model.add_boolean_variable(name=f"{obj.name}_flat_down_stop_{time}")

                if timing_params["T_stable"] >= 1 and (timing_params["T_start"] >= 1 or timing_params["T_stop"] >= 1):
                    q_max = max_power
                    q_min = -q_max
                    model.add_continuous_variable(
                        name=f"{obj.name}_dd_{time}",
                        lower_bound=q_min,
                        upper_bound=q_max,
                    )

                if timing_params["T_stop"] >= 1 and timing_params["T_start"] >= 1 and timing_params["T_stable"] == 0:
                    model.add_boolean_variable(name=f"{obj.name}_down_to_stop_{time}")

                # Reserve variables
                self._add_reserve_variables(
                    model,
                    obj.name,
                    time,
                    min_power,
                    max_power,
                    maximum_automated,
                    relaxed_reserves=True,
                    storage_equipment=False,
                    thermal_equipment=True,
                )

    def _calculate_thermal_timing_params(self, obj: Thermal) -> dict:
        """Calculate timing parameters for thermal equipment."""
        # Convert time constraints to time steps

        # Calculate T_on
        if obj.minimum_time_on != 0:
            T_on = int(max(1, math.ceil(obj.minimum_time_on * 60.0 / self.parameters.timestep))) + 1
        else:
            T_on = 0

        # Calculate T_off
        if obj.minimum_time_off != 0:
            T_off = int(max(1, math.ceil(obj.minimum_time_off * 60.0 / self.parameters.timestep))) + 1
        else:
            T_off = 0

        # Calculate other timing parameters
        T_start = int(math.floor(obj.startup_duration * 60.0 / self.parameters.timestep))
        T_stop = int(math.floor(obj.shutdown_duration * 60.0 / self.parameters.timestep))

        # Calculate T_stable
        if obj.minimum_stable_power_duration * 60.0 < self.parameters.timestep:
            T_stable = 0
        else:
            T_stable = int(math.ceil(obj.minimum_stable_power_duration * 60.0 / self.parameters.timestep)) + 1

        # Rescale T_stable so that it is either equal to 0 or >= 2
        T_stable = T_stable if T_stable >= 2 else 0

        # Calculate T_traceback
        T_traceback = int(max(T_on + T_start, T_off + T_stop))

        return {
            "T_on": T_on,
            "T_off": T_off,
            "T_start": T_start,
            "T_stop": T_stop,
            "T_stable": T_stable,
            "T_traceback": T_traceback,
        }

    def _get_thermal_optimization_times(self, obj: Thermal, timing_params: dict) -> list[DateTime]:
        """Get the optimization time frame for thermal equipment."""
        # Create extended time frame similar to the legacy code
        T_traceback = timing_params["T_traceback"]

        # This would need to be adapted based on your actual time frame creation logic
        # For now, returning the thermal_op_times from parameters
        return self.parameters.thermal_op_times

    def _build_hydro_variables(self, model: OptimisationModel, equipments: list[Hydro]):
        """Build variables for hydro equipment."""
        for obj in equipments:
            for time in self.parameters.hydraulic_op_times:
                min_power = get_minimum_power(obj, time)
                max_power = get_maximum_power(obj, time)
                max_energy = get_maximum_energy(obj, time)
                maximum_automated = get_maximum_automated(obj)

                # Basic variables
                model.add_continuous_variable(
                    name=f"{obj.name}_stored_energy_{time}",
                    lower_bound=0,
                    upper_bound=max_energy,
                )

                self._add_variable_fragment(model, obj, time, self.parameters)

                self._add_reserve_variables(
                    model,
                    obj.name,
                    time,
                    min_power,
                    max_power,
                    maximum_automated,
                    relaxed_reserves=True,
                    storage_equipment=False,
                    thermal_equipment=False,
                )

    def _build_solar_wind_variables(self, model: OptimisationModel, equipments: list[Solar | Wind]):
        """Build variables for solar and wind equipment."""
        for obj in equipments:
            for time in self.parameters.target_times:
                max_power = get_maximum_power(obj, time)
                min_power = get_minimum_power(obj, time)
                maximum_automated = obj.maximum_afrr + obj.maximum_fcr

                model.add_continuous_variable(
                    name=f"{obj.name}_power_level_{time}",
                    lower_bound=0,
                    upper_bound=max_power,
                )

                self._add_reserve_variables(
                    model,
                    obj.name,
                    time,
                    min_power,
                    max_power,
                    maximum_automated,
                    relaxed_reserves=False,
                    storage_equipment=False,
                    thermal_equipment=False,
                )

    def _build_storage_variables(self, model: OptimisationModel, equipments: list[Storage]):
        """Build variables for storage equipment."""

        for obj in equipments:
            optimisation_times: list[DateTime] = self.parameters.storage_mapping[obj.storage_type]["optimisation_times"]
            nbr_fragment: int = self.parameters.storage_mapping[obj.storage_type]["fragment"]

            for time in optimisation_times:
                min_power = get_minimum_power(obj, time)
                max_power = get_maximum_power(obj, time)
                maximum_energy = get_maximum_energy(time)
                maximum_automated = obj.maximum_afrr + obj.maximum_fcr

                # Basic storage variables
                model.add_continuous_variable(
                    name=f"{obj.name}_power_level_sell_{time}",
                    lower_bound=0,
                    upper_bound=max_power,
                )
                model.add_continuous_variable(
                    name=f"{obj.name}_power_level_buy_{time}",
                    lower_bound=min_power,
                    upper_bound=0,
                )
                model.add_boolean_variable(
                    name=f"{obj.name}_is_sell_{time}",
                )
                model.add_continuous_variable(
                    name=f"{obj.name}_stored_energy_{time}",
                    lower_bound=obj.minimum_state_of_charge.get_value(time) * maximum_energy,
                    upper_bound=maximum_energy,
                )

                # Fragment variables
                for n in range(nbr_fragment):
                    model.add_continuous_variable(
                        name=f"{obj.name}_power_level_sell_n_{n}_time_{time}",
                        lower_bound=0,
                        upper_bound=max_power,
                    )
                    model.add_continuous_variable(
                        name=f"{obj.name}_power_level_buy_n_{n}_time_{time}",
                        lower_bound=min_power,
                        upper_bound=0,
                    )

                # Reserve variables for storage
                self._add_reserve_variables(
                    model,
                    obj.name,
                    time,
                    min_power,
                    max_power,
                    maximum_automated,
                    relaxed_reserves=False,
                    storage_equipment=True,
                    thermal_equipment=False,
                )

    def _build_load_variables(self, model: OptimisationModel, equipments: list[Load]):
        """Build variables for load equipment."""
        for obj in equipments:
            for time in self.parameters.target_times:
                max_power = get_maximum_power(obj, time, self.parameters.execution_date)

                model.add_continuous_variable(
                    f"{obj.name}_power_level_{time}",
                    lower_bound=0,
                    upper_bound=max_power,
                )

    def _add_reserve_variables(
        self,
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
            lower_bound=min_power,
            upper_bound=max_power,
        )
        model.add_continuous_variable(
            name=f"unprovided_reserves_up_{name}_{time}",
            lower_bound=0,
            upper_bound=max_power,
        )
        model.add_continuous_variable(
            name=f"unprovided_reserves_down_{name}_{time}",
            lower_bound=min_power,
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
                lower_bound=min_power,
                upper_bound=0,
            )

    def _add_variable_fragment(
        self,
        model: OptimisationModel,
        obj: Hydro,
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

    def get_sum_power_level_variables(
        self,
        model: OptimisationModel,
        equipments: dict[str, list[type[Equipment]]],
        time: DateTime,
    ) -> float:
        """Get the sum of all power level variables for a specific time."""
        total_power = 0

        # Hydro equipment - uses hydraulic_op_times and fragment variables
        if "hydro" in equipments and time in self.parameters.hydraulic_op_times:
            for obj in equipments["hydro"]:
                fragment_data = _get_fragment_data(obj)
                for category in fragment_data.keys():
                    var = model.get_variable(f"{obj.name}_power_level_frag_{category}_at_{time}")
                    if var is not None:
                        total_power += var

        # Solar and Wind equipment - uses target_times
        if time in self.parameters.target_times:
            for equipment_type in ["solar", "wind"]:
                if equipment_type in equipments:
                    for obj in equipments[equipment_type]:
                        var = model.get_variable(f"{obj.name}_power_level_{time}")
                        if var is not None:
                            total_power += var

            # Load equipment - uses target_times
            if "load" in equipments:
                for obj in equipments["load"]:
                    var = model.get_variable(f"{obj.name}_power_level_{time}")
                    if var is not None:
                        total_power += var

        # Thermal equipment - uses thermal_op_times
        if "thermal" in equipments and time in self.parameters.thermal_op_times:
            for obj in equipments["thermal"]:
                var = model.get_variable(f"{obj.name}_power_level_{time}")
                if var is not None:
                    total_power += var

        if "storage" in equipments:
            for obj in equipments["storage"]:
                optimisation_times = self.parameters.storage_mapping[obj.storage_type].get("optimisation_times", [])
                if time in optimisation_times:
                    # Storage has both sell and buy power levels
                    sell_var = model.get_variable(f"{obj.name}_power_level_sell_{time}")
                    buy_var = model.get_variable(f"{obj.name}_power_level_buy_{time}")

                    if sell_var is not None:
                        total_power += sell_var
                    if buy_var is not None:
                        total_power += buy_var

        return total_power

    def _compute_residual_energy(self, equipments: dict[str, list[type[Equipment]]], time: DateTime) -> float:
        """Compute residual energy metrics for all times."""

        residual_energy = self._compute_non_dispatchable_production_residual_energy(
            equipments.get("non_dispatchable_production", []), time
        )
        residual_energy += self._compute_non_dispatchable_load_residual_energy(
            equipments.get("non_dispatchable_load", []), time
        )
        residual_energy += self._compute_dispatchable_residual_energy(equipments, time)

        return residual_energy

    def _compute_power_and_energy(
        self,
        equipments: dict[str, list[type[Equipment]]],
        time: DateTime,
    ) -> tuple[float, float]:
        """Compute maximum power and energy metrics for all times."""
        sum_maximum_power = 0
        sum_max_energy = 0
        equipment_types = ["dispatchable_load", "wind", "solar", "thermal", "hydro", "storage"]

        for equipment_type in equipment_types:
            for obj in equipments.get(equipment_type, []):
                power = get_maximum_power(obj, time, self.parameters.execution_date)
                sum_maximum_power += power
                sum_max_energy += abs(power)

        return sum_maximum_power, sum_max_energy

    def _compute_reserves_and_power_for_time(
        self,
        equipments: dict[str, list[Equipment]],
        time: DateTime,
    ) -> tuple[float, float, float, float, float, float]:
        """Compute reserves and power metrics for a specific time."""
        sum_reserves_up = 0
        sum_reserves_down = 0
        sum_automated_reserves_up = 0
        sum_automated_reserves_down = 0
        sum_maximum_power = 0
        sum_maximum_energy = 0

        equipment_types = ["dispatchable_load", "wind", "solar", "thermal", "hydro", "storage"]

        for equipment_type in equipment_types:
            for obj in equipments.get(equipment_type, []):
                sum_maximum_power += get_maximum_power(obj, time, self.parameters.execution_date)
                sum_maximum_energy += abs(get_maximum_power(obj, time, self.parameters.execution_date))

                (
                    sum_reserves_up,
                    sum_reserves_down,
                    sum_automated_reserves_up,
                    sum_automated_reserves_down,
                    sum_maximum_power,
                ) = get_reserve(
                    obj,
                    sum_reserves_up,
                    sum_reserves_down,
                    sum_automated_reserves_up,
                    sum_automated_reserves_down,
                    sum_maximum_power,
                    time,
                    self.parameters,
                )

        return (
            sum_reserves_up,
            sum_reserves_down,
            sum_automated_reserves_up,
            sum_automated_reserves_down,
            sum_maximum_power,
            sum_maximum_energy,
        )

    def _compute_dispatchable_residual_energy(
        self,
        equipments: dict[str, list[type[Equipment]]],
        time: DateTime,
    ) -> float:
        """Compute residual energy for dispatchable equipment."""
        residual_energy = 0
        equipment_types = ["dispatchable_load", "wind", "solar", "thermal", "hydro", "storage"]

        for equipment_type in equipment_types:
            for obj in equipments.get(equipment_type, []):
                upstream_energy = self._get_upstream_energy(obj, time)
                residual_energy += upstream_energy

        return residual_energy

    def _compute_non_dispatchable_production_residual_energy(
        self,
        equipments: list[OtherNonDispatchable],
        time: DateTime,
    ) -> float:
        """Compute non-dispatchable production equipment residual energy"""
        residual_energy = 0

        for obj in equipments:
            last_forecast_ti = obj.maximum_power_forecast.get_forecast(
                self.parameters.execution_date, self.parameters.start_date, self.parameters.end_date
            ).get_value(time)

            upstream_sold_energy = self._get_upstream_energy(obj, time)
            optimal_dispatch = min(last_forecast_ti, upstream_sold_energy)
            residual_energy += upstream_sold_energy - optimal_dispatch

        return residual_energy

    def _compute_non_dispatchable_load_residual_energy(
        self,
        equipments: list[Load],
        time: DateTime,
    ) -> float:
        """Compute non-dispatchable load equipment residual energy"""
        residual_energy = 0

        for obj in equipments:
            last_forecast_ti = obj.maximum_power_forecast.get_forecast(
                self.parameters.execution_date, self.parameters.start_date, self.parameters.end_date
            ).get_value(time)

            upstream_bought_energy = self._get_upstream_energy(obj, time)
            optimal_dispatch = min(last_forecast_ti, upstream_bought_energy)
            residual_energy += upstream_bought_energy - optimal_dispatch

        return residual_energy

    def _get_upstream_energy(self, obj: type[Equipment], time: DateTime) -> float:
        """Get upstream energy (bought or sold) based on market type."""
        if self.parameters.market == MarketEnum.rr_activation:
            return obj.rr_activated.get_value(time)
        elif self.parameters.market == MarketEnum.mfrr_activation:
            return obj.mfrr_activated.get_value(time)
        else:
            return obj.total_id_cleared_quantity.get_value(time) + obj.da_cleared_quantity.get_value(time)

    def _add_imbalance_variables(
        self,
        model: OptimisationModel,
        portfolio_name: str,
        time: DateTime,
        residual_energy: float,
        maximum_energy: float,
    ):
        """Add imbalance variables to the optimization model."""
        small_imbalance_limit = maximum_energy * self.parameters.small_imbalance_size
        max_overall_imbal = max(residual_energy * self.parameters.maximum_imbalance)

        model.add_continuous_variable(
            name=f"{portfolio_name}_small_imbalance_up_{time}",
            lower_bound=0,
            upper_bound=small_imbalance_limit,
        )
        model.add_continuous_variable(
            name=f"{portfolio_name}_small_imbalance_down_{time}",
            lower_bound=0,
            upper_bound=small_imbalance_limit,
        )
        model.add_continuous_variable(
            name=f"{portfolio_name}_large_imbalance_up_{time}",
            lower_bound=0,
            upper_bound=max_overall_imbal,
        )
        model.add_continuous_variable(
            name=f"{portfolio_name}_large_imbalance_down_{time}",
            lower_bound=0,
            upper_bound=max_overall_imbal,
        )

    def _add_contract_difference_variables(
        self,
        model: OptimisationModel,
        portfolio_name: str,
        time: DateTime,
        maximum_power: float,
    ):
        """Add contract difference variables to the optimization model."""
        contract_vars = [
            "contracted_diff_up",
            "contracted_diff_down",
            "auto_contracted_diff_up",
            "auto_contracted_diff_down",
        ]

        for var_type in contract_vars:
            model.add_continuous_variable(
                name=f"{var_type}_{portfolio_name}_{time}",
                lower_bound=0,
                upper_bound=maximum_power,
            )
