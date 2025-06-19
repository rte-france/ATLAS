from atlas.models.portfolio import Portfolio


class ConstraintBuilder:
    """Builds optimization constraints."""

    def __init__(self, parameters):
        self.parameters = parameters

    def build_constraints(self, portfolio: Portfolio, optimization_times: dict[str, list]) -> tuple[list, list]:
        """Build all constraints for the optimization problem."""
        constraint_list = API.Solver.CreateListOpConstraint()
        global_constraint_list = API.Solver.CreateListOpConstraint()

        max_op_time = self._get_longest_optimization_period(optimization_times)

        for time in max_op_time:
            self._build_time_constraints(time, portfolio, constraint_list, global_constraint_list, optimization_times)

        return constraint_list, global_constraint_list

    def _get_longest_optimization_period(self, optimization_times: dict[str, list]) -> list:
        """Get the longest optimization time period."""
        return max(optimization_times.values(), key=len)

    def _build_time_constraints(
        self,
        time,
        portfolio: Portfolio,
        constraint_list: list,
        global_constraint_list: list,
        optimization_times: dict[str, list],
    ):
        """Build constraints for a specific time period."""
        sum_power_level = API.Solver.CreateListOpVariable()
        reserve_vars = self._initialize_reserve_variables()

        # Add equipment-specific constraints
        self._add_equipment_constraints(
            time, portfolio, constraint_list, sum_power_level, reserve_vars, optimization_times
        )

        # Add global portfolio constraints
        if time in self.parameters.target_times:
            self._add_global_constraints(time, portfolio, global_constraint_list, sum_power_level, reserve_vars)

    def _initialize_reserve_variables(self) -> dict[str, list]:
        """Initialize reserve-related variables."""
        return {
            "up": API.Solver.CreateListOpVariable(),
            "down": API.Solver.CreateListOpVariable(),
            "automated_up": API.Solver.CreateListOpVariable(),
            "automated_down": API.Solver.CreateListOpVariable(),
        }

    def _add_equipment_constraints(
        self,
        time,
        portfolio: Portfolio,
        constraint_list: list,
        sum_power_level: list,
        reserve_vars: dict[str, list],
        optimization_times: dict[str, list],
    ):
        """Add constraints for different equipment types."""
        obj_function = API.Solver.CreateListOpAffineExpression()

        # Wind and PV constraints
        if time in optimization_times.get("op_times", []):
            for equipment_dict in [portfolio.wind, portfolio.pv]:
                GetVariablesAndConstraints_wind_pv(
                    time,
                    equipment_dict,
                    obj_function,
                    constraint_list,
                    sum_power_level,
                    reserve_vars["up"],
                    reserve_vars["down"],
                    reserve_vars["automated_up"],
                    reserve_vars["automated_down"],
                    portfolio.priceForecast,
                    self.parameters,
                )

        # Thermal constraints
        if time in optimization_times.get("thermal_op_times", []):
            GetVariablesAndConstraints_Thermics(
                time,
                portfolio.thermics,
                obj_function,
                constraint_list,
                sum_power_level,
                reserve_vars["up"],
                reserve_vars["down"],
                reserve_vars["automated_up"],
                reserve_vars["automated_down"],
                portfolio.priceForecast,
                self.parameters,
            )

        # Hydraulic constraints
        if time in optimization_times.get("hydraulic_op_times", []):
            GetVariablesAndConstraints_Hydraulics(
                time,
                portfolio.hydraulics,
                obj_function,
                constraint_list,
                sum_power_level,
                reserve_vars["up"],
                reserve_vars["down"],
                reserve_vars["automated_up"],
                reserve_vars["automated_down"],
                portfolio.priceForecast,
                self.parameters,
            )

        # Storage constraints
        storage_times = ["battery_op_times", "phs_op_times", "ev_op_times"]
        if any(time in optimization_times.get(st, []) for st in storage_times):
            GetVariablesAndConstraints_Storage(
                time,
                portfolio.storage,
                obj_function,
                constraint_list,
                sum_power_level,
                reserve_vars["up"],
                reserve_vars["down"],
                reserve_vars["automated_up"],
                reserve_vars["automated_down"],
                portfolio.priceForecast,
                self.parameters,
            )

        # Load constraints
        if time in optimization_times.get("op_times", []):
            GetVariablesAndConstraints_load(
                time,
                portfolio.load,
                obj_function,
                constraint_list,
                sum_power_level,
                reserve_vars["up"],
                reserve_vars["down"],
                reserve_vars["automated_up"],
                reserve_vars["automated_down"],
                portfolio.priceForecast,
                self.parameters,
            )

    def _add_global_constraints(
        self,
        time,
        portfolio: Portfolio,
        global_constraint_list: list,
        sum_power_level: list,
        reserve_vars: dict[str, list],
    ):
        """Add global portfolio constraints."""
        # Power balance constraint
        global_constraint_list.Add(
            portfolio.Small_imbal_up[time]
            + portfolio.Large_imbal_up[time]
            - portfolio.Small_imbal_down[time]
            - portfolio.Large_imbal_down[time]
            == portfolio.residualEnergy[time] - API.Solver.OpSum(sum_power_level)
        )

        # Imbalance limits
        global_constraint_list.Add(
            portfolio.Small_imbal_up[time] + portfolio.Large_imbal_up[time] <= portfolio.max_overall_imbal[time]
        )
        global_constraint_list.Add(
            portfolio.Small_imbal_down[time] + portfolio.Large_imbal_down[time] <= portfolio.max_overall_imbal[time]
        )
