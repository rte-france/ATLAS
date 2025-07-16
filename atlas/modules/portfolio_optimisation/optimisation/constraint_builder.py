from typing import Any, cast

from pendulum import DateTime

from atlas.models.equipment.equipment import Equipment
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.models.solar import SolarPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.wind import WindPO
from atlas.modules.portfolio_optimisation.optimisation.variable_builder import (
    VariableBuilder,
    get_sum_power_level_variables,
)
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_power, get_reserve
from atlas.solver.solver_interface import OptimisationModel


class ConstraintBuilder:
    """Builds optimization constraints."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters
        self.variable_builder = VariableBuilder(self.parameters)

    def build_constraints(
        self,
        portfolio: PortfolioPO,
        max_optimisation_times: list[DateTime],
        optimisation_times: dict[str, list[DateTime]],
        model: OptimisationModel,
    ) -> None:
        """Build all constraints for the optimization problem."""

        for time in max_optimisation_times:
            self._build_time_constraints(time, portfolio, portfolio.name, model, optimisation_times)

    def _build_time_constraints(
        self,
        time: DateTime,
        portfolio: PortfolioPO,
        model: OptimisationModel,
        optimisation_times: dict[str, list[DateTime]],
    ):
        """Build constraints for a specific time period."""

        # Add equipment-specific constraints
        self._add_equipment_constraints(
            time,
            portfolio,
            model,
            optimisation_times,
        )

        if time in self.parameters.target_times:
            self._add_global_constraints(time, portfolio.name, portfolio, model)
            if any(portfolio.get(tech, []) for tech in ["thermal", "hydro", "storage", "wind", "solar"]):
                self._add_reserves_constraints(time, portfolio.name, portfolio, model)

    def _add_equipment_constraints(
        self,
        time: DateTime,
        portfolio: PortfolioPO,
        model: OptimisationModel,
        optimisation_times: dict[str, list[DateTime]],
    ):
        """Add constraints for different equipment types."""

        # Wind and PV constraints
        if time in optimisation_times.get("op_times", []):
            for obj in cast(
                list[WindPO | SolarPO], portfolio.equipments.get("wind", []) + portfolio.equipments.get("solar", [])
            ):
                obj.add_constraints(time, model, self.parameters)

        # Thermal constraints
        # if time in optimisation_times.get("thermal_op_times", []):
        #     for thermal in cast(list[ThermalPO],  portfolio.equipments.get("thermal", [])):
        #         thermal.add_constraints(time, model, self.parameters)

        # Hydraulic constraints
        if time in optimisation_times.get("hydraulic_op_times", []):
            for hydro in cast(list[HydroPO], portfolio.equipments.get("hydro", [])):
                hydro.add_constraints(time, model, self.parameters)

        # Storage constraints
        storage_times = ["battery_op_times", "phs_op_times", "ev_op_times"]
        if any(time in optimisation_times.get(st, []) for st in storage_times):
            for storage in cast(list[StoragePO], portfolio.equipments.get("storage", [])):
                storage.add_contraints(time, model, self.parameters)

        # Load constraints
        if time in optimisation_times.get("op_times", []):
            for load in cast(list[LoadPO], portfolio.equipments.get("load", [])):
                load.add_constraints(time, model, self.parameters)

    def _add_reserves_constraints(
        self,
        time: DateTime,
        portfolio: PortfolioPO,
        model: OptimisationModel,
    ):
        sum_reserves_up_var = sum(
            model.get_variable(f"reserves_up_{obj.name}_{time}")
            for t in portfolio.equipments
            for obj in portfolio.equipments[t]
        )
        sum_reserves_down_var = sum(
            model.get_variable(f"reserves_down_{obj.name}_{time}")
            for t in portfolio.equipments
            for obj in portfolio.equipments[t]
        )
        sum_automated_reserves_up_var = sum(
            model.get_variable(f"automated_reserves_up_{obj.name}_{time}")
            for t in portfolio.equipments
            for obj in portfolio.equipments[t]
        )
        sum_automated_reserves_down_var = sum(
            model.get_variable(f"automated_reserves_down_{obj.name}_{time}")
            for t in portfolio.equipments
            for obj in portfolio.equipments[t]
        )

        (
            reserves_up,
            reserves_down,
            automated_reserves_up,
            automated_reserves_down,
            maximum_power,
            maximum_energy,
        ) = self._compute_reserves_and_power_for_time(time=time, equipments=portfolio)
        model.add_constraint(
            model.get_variable(f"contracted_diff_up_{portfolio.name}_{time}" >= reserves_up - sum_reserves_up_var)
        )
        model.add_constraint(
            model.get_variable(f"contracted_diff_down_{portfolio.name}_{time}" >= reserves_down - sum_reserves_down_var)
        )
        model.add_constraint(
            model.get_variable(
                f"auto_contracted_diff_up_{portfolio.name}_{time}"
                >= automated_reserves_up - sum_automated_reserves_up_var
            )
        )
        model.add_constraint(
            model.get_variable(
                f"auto_contracted_diff_down_{portfolio.name}_{time}"
                >= automated_reserves_down - sum_automated_reserves_down_var
            )
        )

    def _add_global_constraints(
        self,
        time: DateTime,
        portfolio: PortfolioPO,
        model: OptimisationModel,
    ):
        """Add global portfolio constraints."""
        # Power balance constraint
        residual_energy = portfolio.compute_residual_energy(portfolio.equipments, time)
        max_overall_imbal = max(residual_energy * self.parameters.maximum_imbalance)
        sum_power_variables = get_sum_power_level_variables(model, portfolio.equipments, time)

        power_balance_constraint = (
            model.get_variable(f"{portfolio.name}_small_imbalance_up_{time}")
            + model.get_variable(f"{portfolio.name}_large_imbalance_up_{time}")
            - model.get_variable(f"{portfolio.name}_small_imbalance_down_{time}")
            - model.get_variable(f"{portfolio.name}_large_imbalance_down_{time}")
            == residual_energy - sum_power_variables
        )
        model.add_constraint(power_balance_constraint, name=f"power_balance_{time}")

        # Imbalance limits
        up_imbalance_limit = (
            model.get_variable(f"{portfolio.name}_small_imbalance_up_{time}")
            + model.get_variable(f"{portfolio.name}_large_imbalance_up_{time}")
            <= max_overall_imbal
        )
        model.add_constraint(up_imbalance_limit, name=f"up_imbalance_limit_{time}")

        down_imbalance_limit = (
            model.get_variable(f"{portfolio.name}_small_imbalance_down_{time}")
            + model.get_variable(f"{portfolio.name}_large_imbalance_down_{time}")
            <= max_overall_imbal
        )
        model.add_constraint(down_imbalance_limit, name=f"down_imbalance_limit_{time}")

    def _get_power_level_variables(
        self, time: DateTime, model: OptimisationModel, portfolio: dict[str, list[type[Equipment]]]
    ) -> list[Any]:
        power_level_variables: list[Any] = []

        for obj in portfolio["load"] + portfolio["wind"] + portfolio["solar"]:
            power_level_variables.append(model.get_variable(f"{obj.name}_power_level_{time}"))

        return power_level_variables

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
