from pendulum import DateTime

import atlas.config as cfg
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class ConstraintBuilder:
    """Builds optimization constraints."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def build_constraints(
        self,
        portfolio: Portfolio,
        optimization_times: dict[str, list],
        model: OptimisationModel,
    ) -> None:
        """Build all constraints for the optimization problem."""

        max_op_time = self._get_longest_optimization_period(optimization_times)

        for time in max_op_time:
            self._build_time_constraints(time, portfolio, model, optimization_times)

    def _get_longest_optimization_period(self, optimization_times: dict[str, list]) -> list:
        """Get the longest optimization time period."""
        return max(optimization_times.values(), key=len)

    def _build_time_constraints(
        self,
        time: DateTime,
        portfolio: Portfolio,
        model: OptimisationModel,
        optimization_times: dict[str, list],
    ):
        """Build constraints for a specific time period."""
        # Track power level variables for summing
        power_level_variables = []
        reserve_vars = self._initialize_reserve_variables()

        # Add equipment-specific constraints
        self._add_equipment_constraints(
            time,
            portfolio,
            model,
            power_level_variables,
            reserve_vars,
            optimization_times,
        )

        # Add global portfolio constraints
        if time in self.parameters.target_times:
            self._add_global_constraints(time, portfolio, model, power_level_variables, reserve_vars)

    def _initialize_reserve_variables(self) -> dict[str, list]:
        """Initialize reserve-related variables."""
        return {
            "up": [],
            "down": [],
            "automated_up": [],
            "automated_down": [],
        }

    def _add_equipment_constraints(
        self,
        time: DateTime,
        portfolio: Portfolio,
        model: OptimisationModel,
        power_level_variables: list,
        reserve_vars: dict[str, list],
        optimization_times: dict[str, list],
    ):
        """Add constraints for different equipment types."""

        # Wind and PV constraints
        if time in optimization_times.get("op_times", []):
            for equipment_dict in [portfolio.wind, portfolio.pv]:
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
                portfolio.thermics,
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
                portfolio.hydraulics,
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
                portfolio.storage,
                model,
                power_level_variables,
            )

        # Load constraints
        if time in optimization_times.get("op_times", []):
            self._add_constraint_load(
                time,
                portfolio.load,
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
        portfolio: Portfolio,
        model: OptimisationModel,
        power_level_variables: list,
        reserve_vars: dict[str, list],
    ):
        """Add global portfolio constraints."""
        # Power balance constraint
        power_sum = sum(power_level_variables) if power_level_variables else 0

        power_balance_constraint = (
            portfolio.small_imbal_up[time]
            + portfolio.large_imbal_up[time]
            - portfolio.small_imbal_down[time]
            - portfolio.large_imbal_down[time]
            == portfolio.residual_energy[time] - power_sum
        )
        model.add_constraint(power_balance_constraint, name=f"power_balance_{time}")

        # Imbalance limits
        up_imbalance_limit = (
            portfolio.small_imbal_up[time] + portfolio.large_imbal_up[time] <= portfolio.max_overall_imbal[time]
        )
        model.add_constraint(up_imbalance_limit, name=f"up_imbalance_limit_{time}")

        down_imbalance_limit = (
            portfolio.small_imbal_down[time] + portfolio.large_imbal_down[time] <= portfolio.max_overall_imbal[time]
        )
        model.add_constraint(down_imbalance_limit, name=f"down_imbalance_limit_{time}")

        # Reserve constraints (if applicable)
        if reserve_vars["up"]:
            total_reserves_up = sum(reserve_vars["up"])
            reserve_up_constraint = total_reserves_up >= portfolio.reserve_up.get(time, 0)
            model.add_constraint(reserve_up_constraint, name=f"reserve_up_{time}")

        if reserve_vars["down"]:
            total_reserves_down = sum(reserve_vars["down"])
            reserve_down_constraint = total_reserves_down >= portfolio.reserve_down.get(time, 0)
            model.add_constraint(reserve_down_constraint, name=f"reserve_down_{time}")

        if reserve_vars["automated_up"]:
            total_automated_reserves_up = sum(reserve_vars["automated_up"])
            automated_reserve_up_constraint = total_automated_reserves_up >= portfolio.automated_reserve_up.get(time, 0)
            model.add_constraint(automated_reserve_up_constraint, name=f"automated_reserve_up_{time}")

        if reserve_vars["automated_down"]:
            total_automated_reserves_down = sum(reserve_vars["automated_down"])
            automated_reserve_down_constraint = total_automated_reserves_down >= portfolio.automated_reserve_down.get(
                time, 0
            )
            model.add_constraint(automated_reserve_down_constraint, name=f"automated_reserve_down_{time}")

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
        for equipment_name, equipment in equipment_dict.items():
            if time in equipment.power_level:
                # Add power level variable to sum
                power_level_variables.append(equipment.power_level[time])

                # Add reserve variables if they exist
                if time in equipment.reserves_up:
                    reserve_up_vars.append(equipment.reserves_up[time])
                if time in equipment.reserves_down:
                    reserve_down_vars.append(equipment.reserves_down[time])
                if time in equipment.automated_reserves_up:
                    automated_reserve_up_vars.append(equipment.automated_reserves_up[time])
                if time in equipment.automated_reserves_down:
                    automated_reserve_down_vars.append(equipment.automated_reserves_down[time])

                # Equipment-specific constraints
                # Power limits
                power_limit_constraint = (
                    equipment.minimum_power[time] <= equipment.power_level[time] <= equipment.maximum_power[time]
                )
                model.add_constraint(power_limit_constraint, name=f"{equipment_name}_power_limit_{time}")

    def _add_constraint_thermal(
        self,
        time,
        thermics_dict,
        power_level_variables: list,
        reserve_up_vars: list,
        reserve_down_vars: list,
        automated_reserve_up_vars: list,
        automated_reserve_down_vars: list,
    ):
        """Add thermal equipment constraints."""
        for _, equipment in thermics_dict.items():
            if time in equipment.power_level:
                power_level_variables.append(equipment.power_level[time])

                # Add reserve variables
                if time in equipment.reserves_up:
                    reserve_up_vars.append(equipment.reserves_up[time])
                if time in equipment.reserves_down:
                    reserve_down_vars.append(equipment.reserves_down[time])
                if time in equipment.automated_reserves_up:
                    automated_reserve_up_vars.append(equipment.automated_reserves_up[time])
                if time in equipment.automated_reserves_down:
                    automated_reserve_down_vars.append(equipment.automated_reserves_down[time])

    def _add_constraint_hydro(
        self,
        time,
        hydraulics_dict,
        model: OptimisationModel,
        power_level_variables: list,
        reserve_up_vars: list,
        reserve_down_vars: list,
    ):
        """Add hydraulic equipment constraints."""
        for equipment_name, equipment in hydraulics_dict.items():
            if time in equipment.power_level:
                power_level_variables.append(equipment.power_level[time])

                # Add reserve variables
                if time in equipment.reserves_up:
                    reserve_up_vars.append(equipment.reserves_up[time])
                if time in equipment.reserves_down:
                    reserve_down_vars.append(equipment.reserves_down[time])

                # Energy storage constraints for hydraulic
                if time in equipment.stored_energy:
                    energy_limit_constraint = (
                        equipment.minimum_energy[time]
                        <= equipment.stored_energy[time]
                        <= equipment.maximum_energy[time]
                    )
                    model.add_constraint(energy_limit_constraint, name=f"{equipment_name}_energy_limit_{time}")

    def _add_constraint_storage(
        self,
        time,
        storage_dict,
        model: OptimisationModel,
        power_level_variables: list,
    ):
        """Add storage equipment constraints."""
        for equipment_name, equipment in storage_dict.items():
            # Storage has both buy and sell power levels
            if time in equipment.power_level_sell:
                power_level_variables.append(equipment.power_level_sell[time])
            if time in equipment.power_level_buy:
                power_level_variables.append(equipment.power_level_buy[time])

            # Energy storage constraints
            if time in equipment.stored_energy:
                energy_limit_constraint = (
                    equipment.minimum_state_of_charge[time] * equipment.maximum_energy[time]
                    <= equipment.stored_energy[time]
                    <= equipment.maximum_energy[time]
                )
                model.add_constraint(energy_limit_constraint, name=f"{equipment_name}_energy_limit_{time}")

    def _add_constraint_load(
        self,
        time,
        load_dict,
        model: OptimisationModel,
        power_level_variables: list,
    ):
        """Add load equipment constraints."""
        for equipment_name, equipment in load_dict.items():
            if time in equipment.power_level:
                # Load power is typically negative (consumption)
                power_level_variables.append(-equipment.power_level[time])

                # Power limits for loads
                power_limit_constraint = (
                    equipment.minimum_power[time] <= equipment.power_level[time] <= equipment.maximum_power[time]
                )
                model.add_constraint(power_limit_constraint, name=f"{equipment_name}_power_limit_{time}")

    def build_and_add_constraints(self, model: OptimisationModel, Portfolio: Portfolio, optimization_times: dict):
        """Build and add all constraints to the model."""
        # Get constraints from original constraint builder
        constraint_list, global_constraint_list = self.build_constraints(Portfolio, optimization_times, model)

        # Convert and add constraints to OptimisationModel
        self._add_constraints(model, constraint_list, "constraint")
        self._add_constraints(model, global_constraint_list, "global_constraint")

    def _add_constraints(self, model: OptimisationModel, constraint_list: list, prefix: str | None = None):
        """Convert API constraints to OR-Tools constraints and add to model."""
        for i, constraint in enumerate(constraint_list):
            if prefix is None:
                prefix = "constraint"
            constraint_name = f"{prefix}_{i}"

            try:
                model.add_constraint(constraint, constraint_name)
            except Exception as e:
                cfg.logger.error(f"Failed to add {prefix} '{constraint_name}': {e}")
                continue
