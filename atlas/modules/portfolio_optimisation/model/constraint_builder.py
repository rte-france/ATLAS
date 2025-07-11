from typing import Any

from pendulum import DateTime

from atlas.models.equipment.equipment import Equipment
from atlas.modules.portfolio_optimisation.model.constraints_utils import (
    add_constraints_hydro,
    add_constraints_load,
    add_constraints_wind_solar,
    add_contraints_storage,
)
from atlas.modules.portfolio_optimisation.model.variable_builder import VariableBuilder
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class ConstraintBuilder:
    """Builds optimization constraints."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters
        self.variable_builder = VariableBuilder(self.parameters)

    def build_constraints(
        self,
        portfolio: dict[str, list[type[Equipment]]],
        portfolio_name: str,
        max_optimisation_times: list[DateTime],
        optimisation_times: dict[str, list[DateTime]],
        model: OptimisationModel,
    ) -> None:
        """Build all constraints for the optimization problem."""

        for time in max_optimisation_times:
            self._build_time_constraints(time, portfolio, portfolio_name, model, optimisation_times)

    def _build_time_constraints(
        self,
        time: DateTime,
        portfolio: dict[str, list[type[Equipment]]],
        portfolio_name: str,
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
            self._add_global_constraints(time, portfolio_name, portfolio, model)
            if any(portfolio.get(tech, []) for tech in ["thermal", "hydro", "storage", "wind", "solar"]):
                self._add_reserves_constraints(time, portfolio_name, portfolio, model)

    def _add_equipment_constraints(
        self,
        time: DateTime,
        portfolio: dict[str, list[type[Equipment]]],
        model: OptimisationModel,
        optimisation_times: dict[str, list[DateTime]],
    ):
        """Add constraints for different equipment types."""

        # Wind and PV constraints
        if time in optimisation_times.get("op_times", []):
            for equipments in [portfolio["wind"], portfolio["solar"]]:
                add_constraints_wind_solar(
                    time,
                    equipments,
                    model,
                )

        # Thermal constraints
        # if time in optimisation_times.get("thermal_op_times", []):
        #     add_constraints_thermal(
        #         time,
        #         portfolio["thermal"],
        #         model,
        #     )

        # Hydraulic constraints
        if time in optimisation_times.get("hydraulic_op_times", []):
            add_constraints_hydro(
                time,
                portfolio["hydro"],
                model,
            )

        # Storage constraints
        storage_times = ["battery_op_times", "phs_op_times", "ev_op_times"]
        if any(time in optimisation_times.get(st, []) for st in storage_times):
            add_contraints_storage(
                time,
                portfolio["storage"],
                model,
            )

        # Load constraints
        if time in optimisation_times.get("op_times", []):
            add_constraints_load(
                time,
                portfolio["load"],
                model,
            )

    def _add_reserves_constraints(
        self, time: DateTime, portfolio_name: str, portfolio: dict[str, list[type[Equipment]]], model: OptimisationModel
    ):
        sum_reserves_up_var = sum(
            model.get_variable(f"reserves_up_{obj.name}_{time}") for t in portfolio for obj in portfolio[t]
        )
        sum_reserves_down_var = sum(
            model.get_variable(f"reserves_down_{obj.name}_{time}") for t in portfolio for obj in portfolio[t]
        )
        sum_automated_reserves_up_var = sum(
            model.get_variable(f"automated_reserves_up_{obj.name}_{time}") for t in portfolio for obj in portfolio[t]
        )
        sum_automated_reserves_down_var = sum(
            model.get_variable(f"automated_reserves_down_{obj.name}_{time}") for t in portfolio for obj in portfolio[t]
        )

        (
            reserves_up,
            reserves_down,
            automated_reserves_up,
            automated_reserves_down,
            maximum_power,
            maximum_energy,
        ) = self.variable_builder._compute_reserves_and_power_for_time(time=time, equipments=portfolio)
        model.add_constraint(
            model.get_variable(f"contracted_diff_up_{portfolio_name}_{time}" >= reserves_up - sum_reserves_up_var)
        )
        model.add_constraint(
            model.get_variable(f"contracted_diff_down_{portfolio_name}_{time}" >= reserves_down - sum_reserves_down_var)
        )
        model.add_constraint(
            model.get_variable(
                f"auto_contracted_diff_up_{portfolio_name}_{time}"
                >= automated_reserves_up - sum_automated_reserves_up_var
            )
        )
        model.add_constraint(
            model.get_variable(
                f"auto_contracted_diff_down_{portfolio_name}_{time}"
                >= automated_reserves_down - sum_automated_reserves_down_var
            )
        )

    def _add_global_constraints(
        self,
        time: DateTime,
        portfolio_name: str,
        equipments: dict[str, list[type[Equipment]]],
        model: OptimisationModel,
    ):
        """Add global portfolio constraints."""
        # Power balance constraint
        residual_energy = self.variable_builder._compute_residual_energy(equipments, time)
        max_overall_imbal = max(residual_energy * self.parameters.maximum_imbalance)
        sum_power_variables = self.variable_builder.get_sum_power_level_variables(model, equipments, time)

        power_balance_constraint = (
            model.get_variable(f"{portfolio_name}_small_imbalance_up_{time}")
            + model.get_variable(f"{portfolio_name}_large_imbalance_up_{time}")
            - model.get_variable(f"{portfolio_name}_small_imbalance_down_{time}")
            - model.get_variable(f"{portfolio_name}_large_imbalance_down_{time}")
            == residual_energy - sum_power_variables
        )
        model.add_constraint(power_balance_constraint, name=f"power_balance_{time}")

        # Imbalance limits
        up_imbalance_limit = (
            model.get_variable(f"{portfolio_name}_small_imbalance_up_{time}")
            + model.get_variable(f"{portfolio_name}_large_imbalance_up_{time}")
            <= max_overall_imbal
        )
        model.add_constraint(up_imbalance_limit, name=f"up_imbalance_limit_{time}")

        down_imbalance_limit = (
            model.get_variable(f"{portfolio_name}_small_imbalance_down_{time}")
            + model.get_variable(f"{portfolio_name}_large_imbalance_down_{time}")
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
