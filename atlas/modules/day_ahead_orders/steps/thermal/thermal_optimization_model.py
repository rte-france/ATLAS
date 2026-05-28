"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Callable
from datetime import datetime

from pendulum import DateTime

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
from atlas.common.optimal_dispatch.reserves import ReserveFactory, ThermalReserveHandler
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes


class ThermalOptimizationModel(OptimisationModel):
    """
    Optimization program for a single thermal unit.

    Physical dispatch variables and constraints are delegated to :class:`ThermalDispatch`.
    Reserve variables and shared constraints (fill-up, relaxed reserve, capacity) are
    delegated to :class:`ThermalReserveHandler`.
    DA-specific logic (contracted differences, objective) is handled here.
    """

    reserves_up_procured: Timeseries
    reserves_down_procured: Timeseries
    feasible_automated_reserves_up_procured: Timeseries
    feasible_automated_reserves_down_procured: Timeseries
    _reserves: ThermalReserveHandler

    def __init__(
        self,
        parameters: DayAheadOrdersParameters,
        thermal_unit: ThermalDAO,
        prices: Timeseries,
        price_type: str,
        solver_options: SolverOptions,
    ):
        """
        :param parameters: a DayAheadOrdersParameters instance
        :type parameters: DayAheadOrdersParameters
        :param thermal_unit: a Thermal instance
        :type thermal_unit: ThermalDAO
        :param prices: a price timeseries based on which optimization will be conducted.
        :type prices: Timeseries
        :param price_type: the price_type
        :type price_type: str
        :param solver_options: the solver options
        :type solver_options: SolverOptions
        """
        super().__init__(
            solver_name=parameters.solver.solver_name,
            name=f"Optimization program for thermal unit {thermal_unit.name}",
            options=solver_options,
        )
        self.parameters: DayAheadOrdersParameters = parameters
        self.thermal_unit: ThermalDAO = thermal_unit
        self.prices: Timeseries = prices
        self.price_type: str = price_type
        self.automated_unsupplied_reserves: float = 0.0
        self._dispatch = ThermalDispatch(thermal_unit)

        temporal = parameters.temporal
        end_date = temporal.end_date + thermal_unit.additional_hours - temporal.timestep
        self.time_frame: list[DateTime] = generate_datetimes(temporal.start_date, end_date, temporal.timestep)

        self._setup_reserves()
        self._reserves = ReserveFactory.for_thermal(thermal_unit, self._dispatch)

    def _cd(self, prefix: str, t: DateTime) -> str:
        return f"{prefix}_{self.thermal_unit.name}_{t}"

    def _load_reserve_forecast(
        self, attribute: ForecastingMatrix | LazyForecastingMatrix | None, end: DateTime
    ) -> Timeseries:
        default = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            end,
            0,
        )
        if attribute:
            return attribute.get_forecast(  # type: ignore[union-attr]
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                end,
            )
        return default

    def _setup_reserves(self) -> None:
        unit = self.thermal_unit
        end = unit.additional_hours + self.parameters.temporal.end_date

        fcr_up = self._load_reserve_forecast(unit.fcr_up_procured, end)
        fcr_down = self._load_reserve_forecast(unit.fcr_down_procured, end)
        afrr_up = self._load_reserve_forecast(unit.afrr_up_procured, end)
        afrr_down = self._load_reserve_forecast(unit.afrr_down_procured, end)
        mfrr_up = self._load_reserve_forecast(unit.mfrr_up_procured, end)
        mfrr_down = self._load_reserve_forecast(unit.mfrr_down_procured, end)
        rr_up = self._load_reserve_forecast(unit.rr_up_procured, end)
        rr_down = self._load_reserve_forecast(unit.rr_down_procured, end)

        maximum_afrr = unit.maximum_afrr if unit.maximum_afrr is not None else 0.0
        maximum_fcr = unit.maximum_fcr if unit.maximum_fcr is not None else 0.0

        self.reserves_up_procured = mfrr_up + rr_up
        self.reserves_down_procured = mfrr_down + rr_down

        afrr_up_f = afrr_up.filter(self.time_frame, inplace=False)
        afrr_down_f = afrr_down.filter(self.time_frame, inplace=False)
        fcr_up_f = fcr_up.filter(self.time_frame, inplace=False)
        fcr_down_f = fcr_down.filter(self.time_frame, inplace=False)

        self.feasible_automated_reserves_up_procured = afrr_up_f.clip(
            upper_bound=maximum_afrr, inplace=False
        ) + fcr_up_f.clip(upper_bound=maximum_fcr, inplace=False)
        self.feasible_automated_reserves_down_procured = afrr_down_f.clip(
            upper_bound=maximum_afrr, inplace=False
        ) + fcr_down_f.clip(upper_bound=maximum_fcr, inplace=False)

        self.automated_unsupplied_reserves += (
            (afrr_up_f - maximum_afrr).clip(lower_bound=0, inplace=False)
            + (fcr_up_f - maximum_fcr).clip(lower_bound=0, inplace=False)
            + (afrr_down_f - maximum_afrr).clip(lower_bound=0, inplace=False)
            + (fcr_down_f - maximum_fcr).clip(lower_bound=0, inplace=False)
        ).sum()

        cfg.logger.debug(f"automated unsupplied reserves : {self.automated_unsupplied_reserves}")

    def add_variables(self) -> None:
        self._dispatch.setup(self, self.parameters)
        self._reserves.setup(self)

        for t in self.time_frame:
            self._dispatch.add_variables(t)
            max_p = self.thermal_unit.maximum_power.get_value(t)
            min_p = self.thermal_unit.minimum_power.get_value(t)
            self._reserves.add_variables(t, max_p, min_p)
            self.add_continuous_variable(self._cd("contracted_difference_up", t), 0, max_p)
            self.add_continuous_variable(self._cd("contracted_difference_down", t), 0, max_p)
            self.add_continuous_variable(self._cd("automated_contracted_difference_up", t), 0, max_p)
            self.add_continuous_variable(self._cd("automated_contracted_difference_down", t), 0, max_p)

    # ── Objective function ───────────────────────────────────────────────────

    def build_objective(self) -> None:
        """Create the objective function for the thermal optimization."""
        self.set_direction("maximize")

        dt_h = self.parameters.temporal.timestep.total_hours()
        manual_pen = self.parameters.manual_unprocured_reserves_penalty * dt_h
        auto_pen = self.parameters.automated_unprocured_reserves_penalty * dt_h

        self.add_objective(
            objective_expr=(
                sum(
                    self._dispatch.power_level_var.get_value(t)
                    * dt_h
                    * (self.prices.get_value(t) - self.thermal_unit.variable_cost.get_value(t))
                    - self._dispatch.turned_on.get_value(t) * self.thermal_unit.startup_cost.get_value(t)
                    - manual_pen
                    * (
                        self.get_variable(self._cd("contracted_difference_up", t))
                        + self.get_variable(self._cd("contracted_difference_down", t))
                    )
                    - auto_pen
                    * (
                        self.get_variable(self._cd("automated_contracted_difference_up", t))
                        + self.get_variable(self._cd("automated_contracted_difference_down", t))
                    )
                    for t in self.time_frame
                )
                - auto_pen * self.automated_unsupplied_reserves
            ),
        )

    # ── Constraints ──────────────────────────────────────────────────────────

    def build_constraints(self) -> None:
        """Build all constraints: physical dispatch, shared reserves, and DA-specific."""
        ts = self.parameters.temporal.timestep
        for t in self.time_frame:
            self._dispatch.add_constraints(self, t, self.parameters)
            self._add_da_contracted_diff_constraints(t)
            self._reserves.add_fill_up_constraints(
                t,
                self._dispatch.power_level_var.get_value(t),
                self.thermal_unit.maximum_power.get_value(t),
                self.thermal_unit.minimum_power.get_value(t),
                self.parameters.epsilon,
            )
            self._reserves.add_relaxed_reserve_constraint(t, self.thermal_unit.minimum_power.get_value(t))
            self._reserves.add_capacity_constraints(t, self.thermal_unit.maximum_power.get_value(t))

        for t in self.time_frame:
            self._dispatch.add_dd_and_gradient_constraints(self, t, t - ts)

        self._add_da_daily_energy_constraint()

    def _add_da_contracted_diff_constraints(self, time: DateTime) -> None:
        self.add_constraint(
            self.get_variable(self._cd("contracted_difference_up", time))
            >= self.reserves_up_procured.get_value(time) - self.get_variable(self._reserves.var("reserves_up", time))
        )
        self.add_constraint(
            self.get_variable(self._cd("contracted_difference_down", time))
            >= self.reserves_down_procured.get_value(time)
            - self.get_variable(self._reserves.var("reserves_down", time))
        )
        self.add_constraint(
            self.get_variable(self._cd("automated_contracted_difference_up", time))
            >= self.feasible_automated_reserves_up_procured.get_value(time)
            - self.get_variable(self._reserves.var("automated_reserves_up", time))
        )
        self.add_constraint(
            self.get_variable(self._cd("automated_contracted_difference_down", time))
            >= self.feasible_automated_reserves_down_procured.get_value(time)
            - self.get_variable(self._reserves.var("automated_reserves_down", time))
        )

    def _add_da_daily_energy_constraint(self) -> None:
        if not self.thermal_unit.has_daily_energy_constraint or self.thermal_unit.maximum_daily_energy is None:
            return
        steps_by_day: dict[datetime, list] = {}
        for t in self.time_frame:
            key = datetime(t.year, t.month, t.day)
            steps_by_day.setdefault(key, []).append(t)
        for day, steps in steps_by_day.items():
            self.add_constraint(
                sum(self._dispatch.power_level_var.get_value(t) for t in steps)
                <= self.thermal_unit.maximum_daily_energy.get_value(day)
                * self.parameters.temporal.timestep.total_days()
                * len(steps),
                f"energy_limit_of_{self.thermal_unit.name}_at_{day}",
            )

    # ── Solution extraction ──────────────────────────────────────────────────

    def _solution_ts(self, getter: Callable[[DateTime], float]) -> Timeseries:
        return Timeseries.from_values(
            start_date=self.parameters.temporal.start_date,
            frequency=self.parameters.temporal.timestep,
            values=[getter(t) for t in self.time_frame],
        )

    def _extract_results(self) -> dict[str, Timeseries]:
        results: dict[str, Timeseries] = {}

        q_star = self._solution_ts(lambda t: self._dispatch.power_level_var.get_model_var(t).solution_value())
        if abs(q_star.min() - 0.0) <= 1e-6 and abs(q_star.max() - 0.0) <= 1e-6:
            cfg.logger.debug(
                f"*** Info *** The optimal solution for the unit {self.thermal_unit.name} is such that "
                "the unit remains offline and delivers no power output."
            )

        results["q"] = q_star
        results["contracted_difference_up"] = self._solution_ts(
            lambda t: self.get_variable(self._cd("contracted_difference_up", t)).solution_value()
        )
        results["contracted_difference_down"] = self._solution_ts(
            lambda t: self.get_variable(self._cd("contracted_difference_down", t)).solution_value()
        )
        results["automated_contracted_difference_up"] = self._solution_ts(
            lambda t: self.get_variable(self._cd("automated_contracted_difference_up", t)).solution_value()
        )
        results["automated_contracted_difference_down"] = self._solution_ts(
            lambda t: self.get_variable(self._cd("automated_contracted_difference_down", t)).solution_value()
        )
        results["ON_UP"] = self._solution_ts(lambda t: self._dispatch.on_up_var.get_model_var(t).solution_value())
        results["ON_DOWN"] = self._solution_ts(lambda t: self._dispatch.on_down_var.get_model_var(t).solution_value())
        results["OFF"] = self._solution_ts(lambda t: self._dispatch.off_var.get_model_var(t).solution_value())

        if self._dispatch._T_start >= 1:
            results["START"] = self._solution_ts(
                lambda t: self._dispatch.on_start_var.get_model_var(t).solution_value()
            )
        if self._dispatch._T_stop >= 1:
            results["STOP"] = self._solution_ts(lambda t: self._dispatch.stop_var.get_model_var(t).solution_value())
        if self._dispatch._T_stable >= 1:
            results["ON_FLAT"] = self._solution_ts(
                lambda t: self._dispatch.on_flat_var.get_model_var(t).solution_value()
            )

        return results

    def solve_optimisation(self) -> dict[str, Timeseries]:
        if self.parameters.solver.export_lp:
            output_path = self.parameters.get_lp_dir()
            output_path.mkdir(parents=True, exist_ok=True)
            lp_file_path = output_path / f"{self.thermal_unit.name}_price_{self.price_type}.lp"
            self.export_model(str(lp_file_path))

        cfg.logger.info(f"Optimisation model '{self.name}' with price type '{self.price_type}'")
        self.solve()

        status = self.solution_info.status if self.solution_info else None
        cfg.logger.debug(f"Solver status: {status}")
        cfg.logger.debug(f"Objective function value: {self._objective}")

        return self._extract_results()
