"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
from atlas.common.optimal_dispatch.reserves.factory import ReserveFactory
from atlas.common.optimal_dispatch.reserves.thermal import ThermalReserveHandler
from atlas.common.optimal_dispatch.steps import AbstractOptimStep
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.thermal.optimisation_result import ThermalOptimisationResult
from atlas.timing import generate_datetimes

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.solver.solver_interface import OptimisationModel


class ThermalDAOStep(AbstractOptimStep[ThermalDAO]):
    """
    LP optimization step for a single thermal unit in the Day-Ahead Orders context.

    Follows the same :class:`~atlas.common.optimal_dispatch.steps.base.AbstractOptimStep`
    contract as PO steps. Physical dispatch is delegated to :class:`ThermalDispatch`;
    reserve handling to :class:`ThermalReserveHandler`. DA-specific contracted-difference
    variables and the price-based objective are implemented here.

    Typical usage::

        step = ThermalDAOStep(thermal, prices, price_type)
        model = OptimisationModel(solver_name, model_name, solver_options)
        step.add_variables(model, parameters)
        step.add_constraints(model, parameters)
        step.add_objective(model, parameters)
        model.solve()
        raw = step.extract_result(parameters)
    """

    def __init__(self, equipment: ThermalDAO, prices: Timeseries, price_type: str) -> None:
        super().__init__(equipment)
        self._prices = prices
        self._price_type = price_type
        self._dispatch = ThermalDispatch(equipment)
        self._reserves: ThermalReserveHandler | None = None
        self._time_frame: list[DateTime] = []
        self._model: OptimisationModel | None = None
        self.automated_unsupplied_reserves: float = 0.0
        self.reserves_up_procured: Timeseries | None = None
        self.reserves_down_procured: Timeseries | None = None
        self.feasible_automated_reserves_up_procured: Timeseries | None = None
        self.feasible_automated_reserves_down_procured: Timeseries | None = None

    def _cd(self, prefix: str, t: DateTime) -> str:
        return f"{prefix}_{self.equipment.name}_{t}"

    def _load_reserve_forecast(
        self,
        attribute: ForecastingMatrix | LazyForecastingMatrix | None,
        end: DateTime,
        parameters: DayAheadOrdersParameters,
    ) -> Timeseries:
        if attribute:
            return attribute.get_forecast(  # type: ignore[union-attr]
                parameters.temporal.execution_date,
                parameters.temporal.start_date,
                end,
            )
        return Timeseries.from_index(
            parameters.temporal.start_date,
            parameters.temporal.timestep,
            end,
            0,
        )

    def _setup_reserves(self, parameters: DayAheadOrdersParameters) -> None:
        unit = self.equipment
        end = unit.additional_hours + parameters.temporal.end_date

        fcr_up = self._load_reserve_forecast(unit.fcr_up_procured, end, parameters)
        fcr_down = self._load_reserve_forecast(unit.fcr_down_procured, end, parameters)
        afrr_up = self._load_reserve_forecast(unit.afrr_up_procured, end, parameters)
        afrr_down = self._load_reserve_forecast(unit.afrr_down_procured, end, parameters)
        mfrr_up = self._load_reserve_forecast(unit.mfrr_up_procured, end, parameters)
        mfrr_down = self._load_reserve_forecast(unit.mfrr_down_procured, end, parameters)
        rr_up = self._load_reserve_forecast(unit.rr_up_procured, end, parameters)
        rr_down = self._load_reserve_forecast(unit.rr_down_procured, end, parameters)

        maximum_afrr = unit.maximum_afrr if unit.maximum_afrr is not None else 0.0
        maximum_fcr = unit.maximum_fcr if unit.maximum_fcr is not None else 0.0

        self.reserves_up_procured = mfrr_up + rr_up
        self.reserves_down_procured = mfrr_down + rr_down

        afrr_up_f = afrr_up.filter(self._time_frame, inplace=False)
        afrr_down_f = afrr_down.filter(self._time_frame, inplace=False)
        fcr_up_f = fcr_up.filter(self._time_frame, inplace=False)
        fcr_down_f = fcr_down.filter(self._time_frame, inplace=False)

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

    def add_variables(self, model: OptimisationModel, parameters: DayAheadOrdersParameters) -> None:  # type: ignore[override]
        self._model = model
        temporal = parameters.temporal
        end_date = temporal.end_date + self.equipment.additional_hours - temporal.timestep
        self._time_frame = generate_datetimes(temporal.start_date, end_date, temporal.timestep)

        self._setup_reserves(parameters)
        self._dispatch.setup(model, parameters)
        self._reserves = ReserveFactory.for_thermal(self.equipment, self._dispatch)
        self._reserves.setup(model)

        for t in self._time_frame:
            self._dispatch.add_variables(t)
            max_p = self.equipment.maximum_power.get_value(t)
            min_p = self.equipment.minimum_power.get_value(t)
            self._reserves.add_variables(t, max_p, min_p)
            model.add_continuous_variable(self._cd("contracted_difference_up", t), 0, max_p)
            model.add_continuous_variable(self._cd("contracted_difference_down", t), 0, max_p)
            model.add_continuous_variable(self._cd("automated_contracted_difference_up", t), 0, max_p)
            model.add_continuous_variable(self._cd("automated_contracted_difference_down", t), 0, max_p)

    def add_constraints(self, model: OptimisationModel, parameters: DayAheadOrdersParameters) -> None:  # type: ignore[override]
        assert self._reserves is not None
        ts = parameters.temporal.timestep
        for t in self._time_frame:
            self._dispatch.add_constraints(model, t, parameters)
            self._add_da_contracted_diff_constraints(model, t)
            self._reserves.add_fill_up_constraints(
                t,
                self._dispatch.power_level_var.get_value(t),
                self.equipment.maximum_power.get_value(t),
                self.equipment.minimum_power.get_value(t),
                parameters.epsilon,
            )
            self._reserves.add_relaxed_reserve_constraint(t, self.equipment.minimum_power.get_value(t))
            self._reserves.add_capacity_constraints(t, self.equipment.maximum_power.get_value(t))

        for t in self._time_frame:
            self._dispatch.add_dd_and_gradient_constraints(model, t, t - ts)

        self._dispatch.add_daily_energy_constraint(model, self._time_frame, parameters.temporal.timestep)

    def add_objective(  # type: ignore[override]
        self,
        model: OptimisationModel,
        parameters: DayAheadOrdersParameters,
        price_forecasts: dict | None = None,
    ) -> None:
        model.set_direction("maximize")

        dt_h = parameters.temporal.timestep.total_hours()
        manual_pen = parameters.manual_unprocured_reserves_penalty * dt_h
        auto_pen = parameters.automated_unprocured_reserves_penalty * dt_h

        model.add_objective(
            objective_expr=(
                sum(
                    self._dispatch.power_level_var.get_value(t)
                    * dt_h
                    * (self._prices.get_value(t) - self.equipment.variable_cost.get_value(t))
                    - self._dispatch.turned_on.get_value(t) * self.equipment.startup_cost.get_value(t)
                    - manual_pen
                    * (
                        model.get_variable(self._cd("contracted_difference_up", t))
                        + model.get_variable(self._cd("contracted_difference_down", t))
                    )
                    - auto_pen
                    * (
                        model.get_variable(self._cd("automated_contracted_difference_up", t))
                        + model.get_variable(self._cd("automated_contracted_difference_down", t))
                    )
                    for t in self._time_frame
                )
                - auto_pen * self.automated_unsupplied_reserves
            ),
        )

    def _add_da_contracted_diff_constraints(self, model: OptimisationModel, time: DateTime) -> None:
        assert self._reserves is not None
        assert self.reserves_up_procured is not None
        assert self.reserves_down_procured is not None
        assert self.feasible_automated_reserves_up_procured is not None
        assert self.feasible_automated_reserves_down_procured is not None

        model.add_constraint(
            model.get_variable(self._cd("contracted_difference_up", time))
            >= self.reserves_up_procured.get_value(time)
            - model.get_variable(self._reserves.var("reserves_up", time))
        )
        model.add_constraint(
            model.get_variable(self._cd("contracted_difference_down", time))
            >= self.reserves_down_procured.get_value(time)
            - model.get_variable(self._reserves.var("reserves_down", time))
        )
        model.add_constraint(
            model.get_variable(self._cd("automated_contracted_difference_up", time))
            >= self.feasible_automated_reserves_up_procured.get_value(time)
            - model.get_variable(self._reserves.var("automated_reserves_up", time))
        )
        model.add_constraint(
            model.get_variable(self._cd("automated_contracted_difference_down", time))
            >= self.feasible_automated_reserves_down_procured.get_value(time)
            - model.get_variable(self._reserves.var("automated_reserves_down", time))
        )

    def extract_result(self, parameters: DayAheadOrdersParameters) -> ThermalOptimisationResult:
        """
        Extract LP variable values from the solved model.

        Must be called after :meth:`add_variables`, :meth:`add_constraints`,
        :meth:`add_objective`, and ``model.solve()``.

        :param parameters: Module parameters, used to build result timeseries.
        :return: Typed LP output.
        :rtype: ThermalOptimisationResult
        """
        assert self._model is not None
        model = self._model

        def sol_ts(getter) -> Timeseries:
            return Timeseries.from_values(
                start_date=parameters.temporal.start_date,
                frequency=parameters.temporal.timestep,
                values=[getter(t) for t in self._time_frame],
            )

        power_output = sol_ts(lambda t: self._dispatch.power_level_var.get_model_var(t).solution_value())

        if abs(power_output.min() - 0.0) <= 1e-6 and abs(power_output.max() - 0.0) <= 1e-6:
            cfg.logger.debug(
                f"*** Info *** The optimal solution for the unit {self.equipment.name} is such that "
                "the unit remains offline and delivers no power output."
            )

        start = sol_ts(lambda t: self._dispatch.on_start_var.get_model_var(t).solution_value()) if self._dispatch._T_start >= 1 else None
        stop = sol_ts(lambda t: self._dispatch.stop_var.get_model_var(t).solution_value()) if self._dispatch._T_stop >= 1 else None
        on_flat = sol_ts(lambda t: self._dispatch.on_flat_var.get_model_var(t).solution_value()) if self._dispatch._T_stable >= 1 else None

        return ThermalOptimisationResult(
            power_output=power_output,
            contracted_difference_up=sol_ts(
                lambda t: model.get_variable(self._cd("contracted_difference_up", t)).solution_value()
            ),
            contracted_difference_down=sol_ts(
                lambda t: model.get_variable(self._cd("contracted_difference_down", t)).solution_value()
            ),
            automated_contracted_difference_up=sol_ts(
                lambda t: model.get_variable(self._cd("automated_contracted_difference_up", t)).solution_value()
            ),
            automated_contracted_difference_down=sol_ts(
                lambda t: model.get_variable(self._cd("automated_contracted_difference_down", t)).solution_value()
            ),
            on_up=sol_ts(lambda t: self._dispatch.on_up_var.get_model_var(t).solution_value()),
            on_down=sol_ts(lambda t: self._dispatch.on_down_var.get_model_var(t).solution_value()),
            off=sol_ts(lambda t: self._dispatch.off_var.get_model_var(t).solution_value()),
            start=start,
            stop=stop,
            on_flat=on_flat,
        )
