from typing import Any

from pendulum import DateTime

from atlas.models.equipment.equipment import Equipment
from atlas.modules.portfolio_optimisation.model.hydro import add_constraints_hydro
from atlas.modules.portfolio_optimisation.model.load import add_constraints_load
from atlas.modules.portfolio_optimisation.model.storage import add_contraints_storage
from atlas.modules.portfolio_optimisation.model.wind_and_solar import add_constraints_wind_solar
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class ConstraintBuilder:
    """Builds optimization constraints."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def build_constraints(
        self,
        portfolio: dict[str, list[type[Equipment]]],
        portfolio_name: str,
        optimization_times: dict[str, list[DateTime]],
        model: OptimisationModel,
    ) -> None:
        """Build all constraints for the optimization problem."""

        max_op_time = self._get_longest_optimization_period(optimization_times)

        for time in max_op_time:
            self._build_time_constraints(time, portfolio, portfolio_name, model, optimization_times)

    def _get_longest_optimization_period(self, optimization_times: dict[str, list[DateTime]]) -> list[DateTime]:
        """Get the longest optimization time period."""
        return max(optimization_times.values(), key=len)

    def _build_time_constraints(
        self,
        time: DateTime,
        portfolio: dict[str, list[type[Equipment]]],
        portfolio_name: str,
        model: OptimisationModel,
        optimization_times: dict[str, list],
    ):
        """Build constraints for a specific time period."""

        # Add equipment-specific constraints
        self._add_equipment_constraints(
            time,
            portfolio,
            model,
            optimization_times,
        )

        if time in self.parameters.target_times:
            self._add_global_constraints(time, portfolio_name, model, power_level_variables)

    def _add_equipment_constraints(
        self,
        time: DateTime,
        portfolio: dict[str, list[type[Equipment]]],
        model: OptimisationModel,
        optimization_times: dict[str, list],
    ):
        """Add constraints for different equipment types."""

        # Wind and PV constraints
        if time in optimization_times.get("op_times", []):
            for equipments in [portfolio["wind"], portfolio["solar"]]:
                add_constraints_wind_solar(
                    time,
                    equipments,
                    model,
                )

        # Thermal constraints
        if time in optimization_times.get("thermal_op_times", []):
            add_constraints_thermal(
                time,
                portfolio["thermal"],
                model,
            )

        # Hydraulic constraints
        if time in optimization_times.get("hydraulic_op_times", []):
            add_constraints_hydro(
                time,
                portfolio["hydro"],
                model,
            )

        # Storage constraints
        storage_times = ["battery_op_times", "phs_op_times", "ev_op_times"]
        if any(time in optimization_times.get(st, []) for st in storage_times):
            add_contraints_storage(
                time,
                portfolio["storage"],
                model,
            )

        # Load constraints
        if time in optimization_times.get("op_times", []):
            add_constraints_load(
                time,
                portfolio["load"],
                model,
            )

    def _add_global_constraints(
        self,
        time: DateTime,
        portfolio_name: str,
        model: OptimisationModel,
        power_level_variables: list[Any],
    ):
        """Add global portfolio constraints."""
        # Power balance constraint
        power_sum = sum(power_level_variables) if power_level_variables else 0

        power_balance_constraint = (
            model.get_variable(f"{portfolio_name}_small_imbalance_up_{time}")
            + model.get_variable(f"{portfolio_name}_large_imbalance_up_{time}")
            - model.get_variable(f"{portfolio_name}_small_imbalance_down_{time}")
            - model.get_variable(f"{portfolio_name}_large_imbalance_down_{time}")
            == portfolio.residual_energy[time] - power_sum
        )
        model.add_constraint(power_balance_constraint, name=f"power_balance_{time}")

        # Imbalance limits
        up_imbalance_limit = (
            model.get_variable(f"{portfolio_name}_small_imbalance_up_{time}")
            + model.get_variable(f"{portfolio_name}_large_imbalance_up_{time}")
            <= portfolio.max_overall_imbal[time]
        )
        model.add_constraint(up_imbalance_limit, name=f"up_imbalance_limit_{time}")

        down_imbalance_limit = (
            model.get_variable(f"{portfolio_name}_small_imbalance_down_{time}")
            + model.get_variable(f"{portfolio_name}_large_imbalance_down_{time}")
            <= portfolio.max_overall_imbal[time]
        )
        model.add_constraint(down_imbalance_limit, name=f"down_imbalance_limit_{time}")

    def _get_power_level_variables(
        self, time: DateTime, model: OptimisationModel, portfolio: dict[str, list[type[Equipment]]]
    ) -> list[Any]:
        power_level_variables: list[Any] = []

        for obj in portfolio["load"] + portfolio["wind"] + portfolio["solar"]:
            power_level_variables.append(model.get_variable(f"{obj.name}_power_level_{time}"))

        return power_level_variables
