from typing import Any

from pendulum import DateTime

from atlas.models.equipment.equipment import Equipment
from atlas.models.equipment.load import Load
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.thermal import Thermal
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
        optimization_times: dict[str, list],
        model: OptimisationModel,
    ) -> None:
        """Build all constraints for the optimization problem."""

        max_op_time = self._get_longest_optimization_period(optimization_times)

        for time in max_op_time:
            self._build_time_constraints(time, portfolio, portfolio_name, model, optimization_times)

    def _get_longest_optimization_period(self, optimization_times: dict[str, list]) -> list:
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
        # Track power level variables for summing
        power_level_variables = []

        # Add equipment-specific constraints
        self._add_equipment_constraints(
            time,
            portfolio,
            model,
            optimization_times,
        )

        # Add global portfolio constraints
        if time in self.parameters.target_times:
            self._add_global_constraints(time, portfolio_name, model, power_level_variables)

    def _add_equipment_constraints(
        self,
        time: DateTime,
        portfolio: dict[str, list[type[Equipment]]],
        model: OptimisationModel,
        power_level_variables: list,
        reserve_vars: dict[str, list],
        optimization_times: dict[str, list],
    ):
        """Add constraints for different equipment types."""

        # Wind and PV constraints
        if time in optimization_times.get("op_times", []):
            for equipment_dict in [portfolio["wind"], portfolio["solar"]]:
                self._add_constraint_solar_wind(
                    time,
                    equipment_dict,
                    model,
                    power_level_variables,
                    reserve_vars["up"],
                    reserve_vars["down"],
                    reserve_vars["automated_up"],
                    reserve_vars["automated_down"],
                    portfolio.price_forecast,
                    self.parameters,
                )

        # Thermal constraints
        if time in optimization_times.get("thermal_op_times", []):
            self._add_constraint_thermal(
                time,
                portfolio["thermal"],
                model,
                power_level_variables,
                reserve_vars["up"],
                reserve_vars["down"],
                reserve_vars["automated_up"],
                reserve_vars["automated_down"],
            )

        # Hydraulic constraints
        if time in optimization_times.get("hydraulic_op_times", []):
            self._add_constraint_hydro(
                time,
                portfolio["hydro"],
                model,
                power_level_variables,
                reserve_vars["up"],
                reserve_vars["down"],
            )

        # Storage constraints
        storage_times = ["battery_op_times", "phs_op_times", "ev_op_times"]
        if any(time in optimization_times.get(st, []) for st in storage_times):
            self._add_constraint_storage(
                time,
                portfolio["storage"],
                model,
                power_level_variables,
            )

        # Load constraints
        if time in optimization_times.get("op_times", []):
            self._add_constraint_load(
                time,
                portfolio["load"],
                model,
                power_level_variables,
                reserve_vars["up"],
                reserve_vars["down"],
                reserve_vars["automated_up"],
                reserve_vars["automated_down"],
            )

    def _add_global_constraints(
        self,
        time: DateTime,
        portfolio_name: str,
        model: OptimisationModel,
        power_level_variables: list[Any],
        reserve_vars: dict[str, list],
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

    def _add_constraint_solar_wind(
        self,
        time: DateTime,
        equipment_dict,
        model: OptimisationModel,
        power_level_variables: list,
        reserve_up_vars: list,
        reserve_down_vars: list,
        automated_reserve_up_vars: list,
        automated_reserve_down_vars: list,
    ):
        """Add wind and PV equipment constraints."""

    def _add_constraint_thermal(
        self,
        time: DateTime,
        equiments: list[Thermal],
        power_level_variables: list,
        reserve_up_vars: list,
        reserve_down_vars: list,
        automated_reserve_up_vars: list,
        automated_reserve_down_vars: list,
    ):
        """Add thermal equipment constraints."""

    def _add_constraint_hydro(
        self,
        time: DateTime,
        equipments: Storage,
        model: OptimisationModel,
        power_level_variables: list,
        reserve_up_vars: list,
        reserve_down_vars: list,
    ):
        """Add hydraulic equipment constraints."""

    def _add_constraint_storage(
        self,
        time: DateTime,
        equipments: Storage,
        model: OptimisationModel,
        power_level_variables: list,
    ):
        """Add storage equipment constraints."""

    def _add_constraint_load(
        self,
        time: DateTime,
        equipments: list[Load],
        model: OptimisationModel,
        power_level_variables: list,
    ):
        """Add load equipment constraints."""
