"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pendulum import DateTime

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
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
    DA-specific logic (reserves, contracted differences, fill-up, objective) is handled here.
    """

    RESERVES_UP_EQUIP_KEY = "reservesUp_equip_"
    RESERVES_DOWN_EQUIP_KEY = "reservesDown_equip_"
    UNPROVIDED_RESERVES_UP_KEY = "unprovidedReservesUp_equip_"
    UNPROVIDED_RESERVES_DOWN_KEY = "unprovidedReservesDown_equip_"
    RELAXED_RESERVES_KEY = "relaxedReserves_equip_"
    AUTOMATED_RESERVES_UP_KEY = "automatedReservesUp_equip_"
    AUTOMATED_RESERVES_DOWN_KEY = "automatedReservesDown_equip_"
    CONTRACTED_DIFFERENCE_UP_KEY = "contractedDifferenceUp_equip_"
    CONTRACTED_DIFFERENCE_DOWN_KEY = "contractedDifferenceDown_equip_"
    AUTOMATED_CONTRACTED_DIFFERENCE_UP_KEY = "automatedContractedDifferenceUp_equip_"
    AUTOMATED_CONTRACTED_DIFFERENCE_DOWN_KEY = "automatedContractedDifferenceDown_equip_"

    reserves_up_procured: Timeseries
    reserves_down_procured: Timeseries
    feasible_automated_reserves_up_procured: Timeseries
    feasible_automated_reserves_down_procured: Timeseries

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
        self.maximum_automated: float = 0.0
        self.automated_unsupplied_reserves: float = 0.0
        self._dispatch = ThermalDispatch(thermal_unit)

        temporal = parameters.temporal
        end_date = temporal.end_date + thermal_unit.additional_hours - temporal.timestep
        self.time_frame: list[DateTime] = generate_datetimes(temporal.start_date, end_date, temporal.timestep)

        self._setup_reserves()

    # ── DA-specific variable name helpers ────────────────────────────────────

    def reserves_up_equip_at(self, t: DateTime) -> str:
        return f"{self.RESERVES_UP_EQUIP_KEY}{self.thermal_unit.name}_at_{t}"

    def reserves_down_equip_at(self, t: DateTime) -> str:
        return f"{self.RESERVES_DOWN_EQUIP_KEY}{self.thermal_unit.name}_at_{t}"

    def unprovided_reserves_up_at(self, t: DateTime) -> str:
        return f"{self.UNPROVIDED_RESERVES_UP_KEY}{self.thermal_unit.name}_at_{t}"

    def unprovided_reserves_down_at(self, t: DateTime) -> str:
        return f"{self.UNPROVIDED_RESERVES_DOWN_KEY}{self.thermal_unit.name}_at_{t}"

    def relaxed_reserves_at(self, t: DateTime) -> str:
        return f"{self.RELAXED_RESERVES_KEY}{self.thermal_unit.name}_at_{t}"

    def automated_reserves_up_at(self, t: DateTime) -> str:
        return f"{self.AUTOMATED_RESERVES_UP_KEY}{self.thermal_unit.name}_at_{t}"

    def automated_reserves_down_at(self, t: DateTime) -> str:
        return f"{self.AUTOMATED_RESERVES_DOWN_KEY}{self.thermal_unit.name}_at_{t}"

    def contracted_difference_up_at(self, t: DateTime) -> str:
        return f"{self.CONTRACTED_DIFFERENCE_UP_KEY}{self.thermal_unit.name}_at_{t}"

    def contracted_difference_down_at(self, t: DateTime) -> str:
        return f"{self.CONTRACTED_DIFFERENCE_DOWN_KEY}{self.thermal_unit.name}_at_{t}"

    def automated_contracted_difference_up_at(self, t: DateTime) -> str:
        return f"{self.AUTOMATED_CONTRACTED_DIFFERENCE_UP_KEY}{self.thermal_unit.name}_at_{t}"

    def automated_contracted_difference_down_at(self, t: DateTime) -> str:
        return f"{self.AUTOMATED_CONTRACTED_DIFFERENCE_DOWN_KEY}{self.thermal_unit.name}_at_{t}"

    # ── Setup ────────────────────────────────────────────────────────────────

    def _load_reserve_forecast(self, attribute: object, end: DateTime) -> Timeseries:
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
        self.maximum_automated = maximum_afrr + maximum_fcr

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

        for t in self.time_frame:
            self._dispatch.add_variables(t)
            max_p = self.thermal_unit.maximum_power.get_value(t)
            min_p = self.thermal_unit.minimum_power.get_value(t)
            self.add_continuous_variable(self.reserves_up_equip_at(t), 0, max_p)
            self.add_continuous_variable(self.reserves_down_equip_at(t), 0, max_p)
            self.add_continuous_variable(self.unprovided_reserves_up_at(t), 0, max_p)
            self.add_continuous_variable(self.unprovided_reserves_down_at(t), 0, max_p)
            self.add_continuous_variable(self.relaxed_reserves_at(t), 0, min_p)
            self.add_continuous_variable(self.automated_reserves_up_at(t), 0, self.maximum_automated)
            self.add_continuous_variable(self.automated_reserves_down_at(t), 0, self.maximum_automated)
            self.add_continuous_variable(self.contracted_difference_up_at(t), 0, max_p)
            self.add_continuous_variable(self.contracted_difference_down_at(t), 0, max_p)
            self.add_continuous_variable(self.automated_contracted_difference_up_at(t), 0, max_p)
            self.add_continuous_variable(self.automated_contracted_difference_down_at(t), 0, max_p)

    # ── Objective function ───────────────────────────────────────────────────

    def create_objective_function(self, direction: Literal["maximize", "minimize"] = "maximize") -> None:
        """
        Create the objective function for the thermal optimization.

        :param direction: the direction of the objective function
        :type direction: Literal["maximize", "minimize"]
        """
        self.set_direction(direction)

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
                        self.get_variable(self.contracted_difference_up_at(t))
                        + self.get_variable(self.contracted_difference_down_at(t))
                    )
                    - auto_pen
                    * (
                        self.get_variable(self.automated_contracted_difference_up_at(t))
                        + self.get_variable(self.automated_contracted_difference_down_at(t))
                    )
                    for t in self.time_frame
                )
                - auto_pen * self.automated_unsupplied_reserves
            ),
        )

    # ── Constraints ──────────────────────────────────────────────────────────

    def build_constraints(self) -> None:
        """Build all constraints: physical dispatch (via ThermalDispatch) and DA-specific."""
        ts = self.parameters.temporal.timestep
        for t in self.time_frame:
            self._dispatch.add_constraints(self, t, self.parameters)
            self._add_da_contracted_diff_constraints(t)
            self._add_da_fill_up_constraints(t)
            self._add_da_relaxed_reserve_constraint(t)
            self._add_da_reserve_capacity_constraints(t)

        for t in self.time_frame:
            self._dispatch.add_dd_and_gradient_constraints(self, t, t - ts)

        self._add_da_daily_energy_constraint()

    def _add_da_contracted_diff_constraints(self, time: DateTime) -> None:
        self.add_constraint(
            self.get_variable(self.contracted_difference_up_at(time))
            >= self.reserves_up_procured.get_value(time) - self.get_variable(self.reserves_up_equip_at(time))
        )
        self.add_constraint(
            self.get_variable(self.contracted_difference_down_at(time))
            >= self.reserves_down_procured.get_value(time) - self.get_variable(self.reserves_down_equip_at(time))
        )
        self.add_constraint(
            self.get_variable(self.automated_contracted_difference_up_at(time))
            >= self.feasible_automated_reserves_up_procured.get_value(time)
            - self.get_variable(self.automated_reserves_up_at(time))
        )
        self.add_constraint(
            self.get_variable(self.automated_contracted_difference_down_at(time))
            >= self.feasible_automated_reserves_down_procured.get_value(time)
            - self.get_variable(self.automated_reserves_down_at(time))
        )

    def _add_da_fill_up_constraints(self, time: DateTime) -> None:
        eps = self.parameters.epsilon
        q = self._dispatch.power_level_var.get_value(time)
        max_p = self.thermal_unit.maximum_power.get_value(time)
        min_p = self.thermal_unit.minimum_power.get_value(time)

        up_sum = (
            q
            + self.get_variable(self.reserves_up_equip_at(time))
            + self.get_variable(self.automated_reserves_up_at(time))
            + self.get_variable(self.unprovided_reserves_up_at(time))
        )
        self.add_constraint(up_sum <= max_p + eps)
        self.add_constraint(up_sum >= max_p - eps)

        down_sum = (
            q
            - self.get_variable(self.reserves_down_equip_at(time))
            - self.get_variable(self.automated_reserves_down_at(time))
            - self.get_variable(self.unprovided_reserves_down_at(time))
            + self.get_variable(self.relaxed_reserves_at(time))
        )
        self.add_constraint(down_sum <= min_p + eps)
        self.add_constraint(down_sum >= min_p - eps)

    def _add_da_relaxed_reserve_constraint(self, time: DateTime) -> None:
        d = self._dispatch
        online_sum = d.on_up_var.get_value(time) + d.on_down_var.get_value(time)
        if d._has_flat:
            online_sum = online_sum + d.on_flat_var.get_value(time)
        self.add_constraint(
            self.get_variable(self.relaxed_reserves_at(time))
            <= self.thermal_unit.minimum_power.get_value(time) * (1 - online_sum)
        )

    def _add_da_reserve_capacity_constraints(self, time: DateTime) -> None:
        d = self._dispatch
        unavailable = d.off_var.get_value(time)
        if d._has_start:
            unavailable = unavailable + d.on_start_var.get_value(time)
        if d._has_stop:
            unavailable = unavailable + d.stop_var.get_value(time)

        self.add_constraint(
            self.get_variable(self.automated_reserves_up_at(time)) <= self.maximum_automated * (1 - unavailable)
        )
        self.add_constraint(
            self.get_variable(self.automated_reserves_down_at(time)) <= self.maximum_automated * (1 - unavailable)
        )

        res_unavailable = unavailable
        if d._has_flat:
            res_unavailable = res_unavailable + d.on_up_var.get_value(time) + d.on_down_var.get_value(time)

        max_p = self.thermal_unit.maximum_power.get_value(time)
        self.add_constraint(
            self.get_variable(self.reserves_up_equip_at(time)) <= max_p * (1 - res_unavailable)
        )
        self.add_constraint(
            self.get_variable(self.reserves_down_equip_at(time)) <= max_p * (1 - res_unavailable)
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

    def _export_lp_if_requested(self) -> None:
        if self.parameters.solver.export_lp:
            output_path = self.parameters.get_lp_dir()
            output_path.mkdir(parents=True, exist_ok=True)
            lp_file_path = output_path / f"{self.thermal_unit.name}_price_{self.price_type}.lp"
            self.export_model(str(lp_file_path))

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
            lambda t: self.get_variable(self.contracted_difference_up_at(t)).solution_value()
        )
        results["contracted_difference_down"] = self._solution_ts(
            lambda t: self.get_variable(self.contracted_difference_down_at(t)).solution_value()
        )
        results["automated_contracted_difference_up"] = self._solution_ts(
            lambda t: self.get_variable(self.automated_contracted_difference_up_at(t)).solution_value()
        )
        results["automated_contracted_difference_down"] = self._solution_ts(
            lambda t: self.get_variable(self.automated_contracted_difference_down_at(t)).solution_value()
        )
        results["ON_UP"] = self._solution_ts(lambda t: self._dispatch.on_up_var.get_model_var(t).solution_value())
        results["ON_DOWN"] = self._solution_ts(lambda t: self._dispatch.on_down_var.get_model_var(t).solution_value())
        results["OFF"] = self._solution_ts(lambda t: self._dispatch.off_var.get_model_var(t).solution_value())

        if self._dispatch._T_start >= 1:
            results["START"] = self._solution_ts(
                lambda t: self._dispatch.on_start_var.get_model_var(t).solution_value()
            )
        if self._dispatch._T_stop >= 1:
            results["STOP"] = self._solution_ts(
                lambda t: self._dispatch.stop_var.get_model_var(t).solution_value()
            )
        if self._dispatch._T_stable >= 1:
            results["ON_FLAT"] = self._solution_ts(
                lambda t: self._dispatch.on_flat_var.get_model_var(t).solution_value()
            )

        return results

    def solve_thermal_optimization(self) -> dict[str, Timeseries]:
        self._export_lp_if_requested()

        cfg.logger.info(f"Optimisation model '{self.name}' with price type '{self.price_type}'")
        self.solve()

        status = self.solution_info.status if self.solution_info else None
        cfg.logger.debug(f"Solver status: {status}")
        cfg.logger.debug(f"Objective function value: {self._objective}")

        return self._extract_results()
