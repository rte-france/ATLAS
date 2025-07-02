from pendulum import DateTime

from atlas.enum import StorageType
from atlas.models.equipment.equipment import Equipment
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.wind import Wind
from atlas.modules.portfolio_optimisation.parameters import MarketEnum, PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.get_fragment_price import add_variable_fragment
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

    def __init__(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        self.model = model
        self.parameters = parameters

    def build_all_variables(
        self,
        portfolio_name: str,
        equipments: dict[str, list[type[Equipment]]],
        times: list[DateTime],
    ):
        """Build all variables for the optimization model."""
        # Build equipment-specific variables
        self._build_equipment_variables(equipments, times)

        # Build portfolio-level variables
        self._build_portfolio_variables(portfolio_name, equipments, times)

    def _build_equipment_variables(
        self,
        equipments: dict[str, list[type[Equipment]]],
        times: list[DateTime],
    ):
        """Build variables for all equipment types."""
        if "hydro" in equipments:
            self._build_hydro_variables(equipments["hydro"])

        if "solar" in equipments:
            self._build_solar_wind_variables(equipments["solar"])

        if "wind" in equipments:
            self._build_solar_wind_variables(equipments["wind"])

        if "storage" in equipments:
            self._build_storage_variables(equipments["storage"])

        if "load" in equipments:
            self._build_load_variables(equipments["load"])

    def _build_portfolio_variables(
        self,
        portfolio_name: str,
        equipments: dict[str, list[type[Equipment]]],
        times: list[DateTime],
    ):
        """Build portfolio-level optimization variables."""

        for time in times:
            residual_energy = self._compute_residual_energy(equipments, time)
            maximum_power, maximum_energy = self._compute_power_and_energy(equipments, time)
            self._add_imbalance_variables(portfolio_name, time, residual_energy, maximum_energy)
            self._add_contract_difference_variables(portfolio_name, time, maximum_power)

    def _build_hydro_variables(self, equipments: list[Hydro]):
        """Build variables for hydro equipment."""
        for obj in equipments:
            for time in self.parameters.hydraulic_op_times:
                min_power = get_minimum_power(obj, time)
                max_power = get_maximum_power(obj, time)
                max_energy = get_maximum_energy(obj, time)
                maximum_automated = get_maximum_automated(obj)

                # Basic variables
                self.model.add_continuous_variable(
                    name=f"{obj.name}_power_level_{time}",
                    lower_bound=0,
                    upper_bound=max_power,
                )
                self.model.add_continuous_variable(
                    name=f"{obj.name}_stored_energy_{time}",
                    lower_bound=0,
                    upper_bound=max_energy,
                )

                add_variable_fragment(obj, time, self.parameters, self.model)

                # Reserve variables
                self._add_reserve_variables(obj.name, time, min_power, max_power, maximum_automated)

    def _build_solar_wind_variables(self, equipments: list[Solar | Wind]):
        """Build variables for solar and wind equipment."""
        for obj in equipments:
            for time in self.parameters.target_times:
                max_power = get_maximum_power(obj, time)
                min_power = get_minimum_power(obj, time)
                maximum_automated = obj.maximum_afrr + obj.maximum_fcr

                self.model.add_continuous_variable(
                    name=f"{obj.name}_power_level_{time}",
                    lower_bound=0,
                    upper_bound=max_power,
                )

                self._add_reserve_variables(obj.name, time, min_power, max_power, maximum_automated)

    def _build_storage_variables(self, equipments: list[Storage]):
        """Build variables for storage equipment."""
        storage_mapping = {
            StorageType.BATTERY: {
                "op_time_frame": self.parameters.battery_op_times,
                "fragment": self.parameters.battery_number_of_fragments,
            },
            StorageType.PUMPED_HYDRAULIC_STORAGE: {
                "op_time_frame": self.parameters.phs_op_times,
                "fragment": self.parameters.pumped_hydraulic_number_of_fragments,
            },
            StorageType.ELECTRIC_VEHICLE: {
                "op_time_frame": self.parameters.ev_op_times,
                "fragment": self.parameters.electric_vehicle_number_of_fragments,
            },
        }

        for obj in equipments:
            op_time_frame = storage_mapping[obj.storage_type]["op_time_frame"]
            nbr_fragment = storage_mapping[obj.storage_type]["fragment"]

            for time in op_time_frame:
                min_power = get_minimum_power(obj, time)
                max_power = get_maximum_power(obj, time)
                maximum_energy = get_maximum_energy(time)
                maximum_automated = obj.maximum_afrr + obj.maximum_fcr

                # Basic storage variables
                self.model.add_continuous_variable(
                    name=f"{obj.name}_power_level_sell_{time}",
                    lower_bound=0,
                    upper_bound=max_power,
                )
                self.model.add_continuous_variable(
                    name=f"{obj.name}_power_level_buy_{time}",
                    lower_bound=min_power,
                    upper_bound=0,
                )
                self.model.add_boolean_variable(
                    name=f"{obj.name}_is_sell_{time}",
                )
                self.model.add_continuous_variable(
                    name=f"{obj.name}_stored_energy_{time}",
                    lower_bound=obj.minimum_state_of_charge.get_value(time) * maximum_energy,
                    upper_bound=maximum_energy,
                )

                # Fragment variables
                for n in range(nbr_fragment):
                    self.model.add_continuous_variable(
                        name=f"{obj.name}_power_level_sell_n_{n}_time_{time}",
                        lower_bound=0,
                        upper_bound=max_power,
                    )
                    self.model.add_continuous_variable(
                        name=f"{obj.name}_power_level_buy_n_{n}_time_{time}",
                        lower_bound=min_power,
                        upper_bound=0,
                    )

                # Reserve variables for storage
                self._add_storage_reserve_variables(obj.name, time, min_power, max_power, maximum_automated)

    def _build_load_variables(self, equipments: list[Load]):
        """Build variables for load equipment."""
        for obj in equipments:
            for time in self.parameters.target_times:
                max_power = get_maximum_power(obj, time, self.parameters.execution_date)

                self.model.add_continuous_variable(
                    f"{obj.name}_power_level_{time}",
                    lower_bound=0,
                    upper_bound=max_power,
                )

    def _add_reserve_variables(
        self, name: str, time: DateTime, min_power: float, max_power: float, maximum_automated: float
    ):
        """Add reserve variables for solar/wind equipment (with 'at' in name)."""
        self.model.add_continuous_variable(
            name=f"reserves_up_{name}_{time}",
            lower_bound=0,
            upper_bound=max_power,
        )
        self.model.add_continuous_variable(
            name=f"reserves_down_{name}_{time}",
            lower_bound=min_power,
            upper_bound=max_power,
        )
        self.model.add_continuous_variable(
            name=f"unprovided_reserves_up_{name}_{time}",
            lower_bound=0,
            upper_bound=max_power,
        )
        self.model.add_continuous_variable(
            name=f"unprovided_reserves_down_{name}_{time}",
            lower_bound=min_power,
            upper_bound=max_power,
        )
        self.model.add_continuous_variable(
            name=f"automated_reserves_up_{name}_{time}",
            lower_bound=0,
            upper_bound=maximum_automated,
        )
        self.model.add_continuous_variable(
            name=f"automated_reserves_down_{name}_{time}",
            lower_bound=0,
            upper_bound=maximum_automated,
        )
        self.model.add_continuous_variable(
            name=f"contracted_diff_up_{name}_{time}",
            lower_bound=0,
            upper_bound=max_power,
        )
        self.model.add_continuous_variable(
            name=f"contracted_diff_down_{name}_{time}",
            lower_bound=min_power,
            upper_bound=max_power,
        )
        self.model.add_continuous_variable(
            name=f"automated_contracted_diff_up_{name}_{time}",
            lower_bound=0,
            upper_bound=max_power,
        )
        self.model.add_continuous_variable(
            name=f"automated_contracted_diff_down_{name}_{time}",
            lower_bound=min_power,
            upper_bound=max_power,
        )

        self.model.add_continuous_variable(
            name=f"relaxed_reserves_{name}_{time}",
            lower_bound=min_power,
            upper_bound=0,
        )

    def _add_storage_reserve_variables(
        self, name: str, time: DateTime, min_power: float, max_power: float, maximum_automated: float
    ):
        """Add reserve variables for storage equipment."""
        self.model.add_continuous_variable(
            name=f"reserves_up_e_{name}_at_{time}",
            lower_bound=0,
            upper_bound=max_power,
        )
        self.model.add_continuous_variable(
            name=f"reserves_down_e_{name}_at_{time}",
            lower_bound=min_power,
            upper_bound=max_power,
        )
        self.model.add_continuous_variable(
            name=f"unprovided_reserves_up_e_{name}_at_{time}",
            lower_bound=0,
            upper_bound=max_power,
        )
        self.model.add_continuous_variable(
            name=f"unprovided_reserves_down_e_{name}_at_{time}",
            lower_bound=min_power,
            upper_bound=max_power,
        )
        self.model.add_continuous_variable(
            name=f"automated_reserves_up_e_{name}_at_{time}",
            lower_bound=0,
            upper_bound=maximum_automated,
        )
        self.model.add_continuous_variable(
            name=f"automated_reserves_down_e_{name}_at_{time}",
            lower_bound=-maximum_automated,
            upper_bound=maximum_automated,
        )

    def _compute_residual_energy(
        self, equipments: dict[str, list[type[Equipment]]], time: DateTime
    ) -> dict[DateTime, float]:
        """Compute residual energy metrics for all times."""

        residual_energy = self._compute_non_dispatchable_production_residual_energy(
            equipments.get("non_dispatchable_production", []), time
        )
        residual_energy += self._compute_non_dispatchable_load_residual_energy(
            equipments.get("non_dispatchable_load", []), time
        )
        residual_energy += self._compute_dispatchable_residual_energy(equipments, time)
        residual_energy[time] = residual_energy

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

    def _compute_reserves_metrics(
        self,
        equipments: dict[str, list[type[Equipment]]],
        times: list[DateTime],
    ) -> tuple[dict, dict, dict, dict]:
        """Compute reserve metrics for all times (if needed elsewhere)."""
        reserve_up = {}
        reserve_down = {}
        automated_reserve_up = {}
        automated_reserve_down = {}

        for time in times:
            (
                sum_reserves_up,
                sum_reserves_down,
                sum_automated_reserves_up,
                sum_automated_reserves_down,
                _,  # maximum_power not needed here
                _,  # maximum_energy not needed here
            ) = self._compute_reserves_and_power_for_time(equipments, time)

            reserve_up[time] = sum_reserves_up
            reserve_down[time] = sum_reserves_down
            automated_reserve_up[time] = sum_automated_reserves_up
            automated_reserve_down[time] = sum_automated_reserves_down

        return reserve_up, reserve_down, automated_reserve_up, automated_reserve_down

    def _compute_reserves_and_power_for_time(
        self,
        equipments: dict[str, list[type[Equipment]]],
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
        portfolio_name: str,
        time: DateTime,
        residual_energy: float,
        maximum_energy: float,
    ):
        """Add imbalance variables to the optimization model."""
        small_imbalance_limit = maximum_energy * self.parameters.small_imbalance_size
        max_overall_imbal = max(residual_energy * self.parameters.maximum_imbalance)

        self.model.add_continuous_variable(
            name=f"{portfolio_name}_small_imbalance_up_{time}",
            lower_bound=0,
            upper_bound=small_imbalance_limit,
        )
        self.model.add_continuous_variable(
            name=f"{portfolio_name}_small_imbalance_down_{time}",
            lower_bound=0,
            upper_bound=small_imbalance_limit,
        )
        self.model.add_continuous_variable(
            name=f"{portfolio_name}_large_imbalance_up_{time}",
            lower_bound=0,
            upper_bound=max_overall_imbal,
        )
        self.model.add_continuous_variable(
            name=f"{portfolio_name}_large_imbalance_down_{time}",
            lower_bound=0,
            upper_bound=max_overall_imbal,
        )

    def _add_contract_difference_variables(
        self,
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
            self.model.add_continuous_variable(
                name=f"{var_type}_{portfolio_name}_{time}",
                lower_bound=0,
                upper_bound=maximum_power,
            )
