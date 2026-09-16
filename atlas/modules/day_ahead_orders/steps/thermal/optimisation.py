"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import polars as pl

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
from atlas.common.optimal_dispatch.reserves.factory import ReserveFactory
from atlas.common.optimal_dispatch.steps import AbstractOptimStep
from atlas.enums import ThermalDispatchState
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.common.optimal_dispatch.reserves.thermal import ThermalReserveHandler
    from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix


_CONTRACTED_DIFFERENCE_PREFIXES = (
    "contracted_difference_up",
    "contracted_difference_down",
    "automated_contracted_difference_up",
    "automated_contracted_difference_down",
)


@dataclass
class ThermalOptimisationResult:
    """
    Solved values of one thermal unit, for one price scenario.

    Only the state variables are kept: order formulation reads the operating regime of the
    unit, never its power output. ``start``, ``stop`` and ``on_flat`` are ``None`` when the
    corresponding phase does not exist for the unit (``T_start``, ``T_stop``, ``T_stable``
    equal to zero), which is how the callers know which states to collapse.

    :param on_up: Unit is online and allowed to ramp up
    :type on_up: Timeseries
    :param on_down: Unit is online and allowed to ramp down
    :type on_down: Timeseries
    :param off: Unit is offline
    :type off: Timeseries
    :param start: Unit is in its startup ramp, ``None`` when it has none
    :type start: Timeseries | None
    :param stop: Unit is in its shutdown ramp, ``None`` when it has none
    :type stop: Timeseries | None
    :param on_flat: Unit is online at a stable power, ``None`` when it has no stable phase
    :type on_flat: Timeseries | None
    """

    on_up: Timeseries = field(default_factory=Timeseries)
    on_down: Timeseries = field(default_factory=Timeseries)
    off: Timeseries = field(default_factory=Timeseries)
    start: Timeseries | None = None
    stop: Timeseries | None = None
    on_flat: Timeseries | None = None


class ThermalDAOStep(AbstractOptimStep[ThermalDAO, DayAheadOrdersParameters]):
    """
    Step owning the day-ahead bidding optimisation of a single thermal unit.

    Composes :class:`~atlas.common.optimal_dispatch.dispatch.thermal.ThermalDispatch` for
    the physical variables and constraints, and
    :class:`~atlas.common.optimal_dispatch.reserves.thermal.ThermalReserveHandler` for the
    reserve ones. What stays here is day-ahead specific: the contracted-difference
    variables (the volume of procured reserve the unit fails to provide), their defining
    constraints, and the price-driven profit objective.

    The unit optimises over a horizon extended by its own ``additional_hours``, so that
    the orders submitted for the delivery day account for the hours that follow it.

    :param equipment: Thermal unit to optimise
    :type equipment: ThermalDAO
    :param prices: Price forecast of the scenario being solved
    :type prices: Timeseries
    """

    def __init__(self, equipment: ThermalDAO, prices: Timeseries) -> None:
        super().__init__(equipment)
        self._prices = prices
        self.dispatch = ThermalDispatch(equipment)
        self._reserves: ThermalReserveHandler = ReserveFactory.for_thermal(equipment, self.dispatch)
        self._time_frame: list[DateTime] = []
        self._model: OptimisationModel | None = None

    @property
    def time_frame(self) -> list[DateTime]:
        """Timesteps the model is built on — empty until :meth:`add_variables` has run."""
        return self._time_frame

    def add_variables(self, model: OptimisationModel, parameters: DayAheadOrdersParameters) -> None:
        self._model = model
        temporal = parameters.temporal
        self._time_frame = generate_datetimes(
            temporal.start_date,
            temporal.end_date + self.equipment.additional_hours - temporal.timestep,
            temporal.timestep,
        )

        self.dispatch.setup(model, parameters)
        self._reserves.setup(model)
        self._reserves.setup_reserve_forecasts(*self._reserve_forecasts(parameters))

        for time in self._time_frame:
            self.dispatch.add_variables(time)
            max_power = self.equipment.maximum_power.get_value(time)
            self._reserves.add_variables(time, max_power, self.equipment.minimum_power.get_value(time))
            for prefix in _CONTRACTED_DIFFERENCE_PREFIXES:
                model.add_continuous_variable(self._var(prefix, time), 0, max_power)

    def add_constraints(self, model: OptimisationModel, parameters: DayAheadOrdersParameters) -> None:
        timestep = parameters.temporal.timestep
        for time in self._time_frame:
            self.dispatch.add_constraints(model, time, parameters)
            self.dispatch.add_dd_and_gradient_constraints(model, time, time - timestep)
            self._add_contracted_difference_constraints(model, time)
            max_power = self.equipment.maximum_power.get_value(time)
            min_power = self.equipment.minimum_power.get_value(time)
            self._reserves.add_fill_up_constraints(
                time,
                self.dispatch.power_level_var.get_value(time),
                max_power,
                min_power,
                parameters.allowed_round_off_error,
            )
            self._reserves.add_relaxed_reserve_constraint(time, min_power)
            self._reserves.add_capacity_constraints(time, max_power)

        self.dispatch.add_daily_energy_constraint(model, self._time_frame, timestep)

    def add_objective(
        self,
        model: OptimisationModel,
        parameters: DayAheadOrdersParameters,
        price_forecasts: dict | None = None,
    ) -> None:
        """
        Maximise the margin of the unit over its horizon.

        Sells its power output at the forecast price minus its variable cost, pays the
        startup cost on every start, and is penalised for every MW of procured reserve it
        does not provide — manual and automated at their own penalty rates. The volume
        that is infeasible from the start (procured beyond the unit's aFRR/FCR capacity)
        is a constant of the model, subtracted once outside the time loop.

        ``price_forecasts`` is unused: the scenario prices are given to the constructor,
        since one step solves exactly one scenario.
        """
        dt_hours = parameters.temporal.timestep.total_hours()
        manual_penalty = parameters.manual_unprocured_reserves_penalty * dt_hours
        automated_penalty = parameters.automated_unprocured_reserves_penalty * dt_hours

        model.add_objective(
            objective_expr=(
                sum(
                    self.dispatch.power_level_var.get_value(time)
                    * dt_hours
                    * (self._prices.get_value(time) - self.equipment.variable_cost.get_value(time))
                    - self.dispatch.turned_on.get_value(time) * self.equipment.startup_cost.get_value(time)
                    - manual_penalty
                    * (
                        model.get_variable(self._var("contracted_difference_up", time))
                        + model.get_variable(self._var("contracted_difference_down", time))
                    )
                    - automated_penalty
                    * (
                        model.get_variable(self._var("automated_contracted_difference_up", time))
                        + model.get_variable(self._var("automated_contracted_difference_down", time))
                    )
                    for time in self._time_frame
                )
                - automated_penalty * self._reserves.automated_unsupplied_reserves
            ),
        )

    def extract_result(self, parameters: DayAheadOrdersParameters) -> ThermalOptimisationResult:
        """
        Read the state variables back from the solved model.

        :param parameters: Module parameters, used to index the result timeseries
        :type parameters: DayAheadOrdersParameters
        :return: Solved states of the unit
        :rtype: ThermalOptimisationResult
        """
        dispatch = self.dispatch

        def solution(getter: Callable[[DateTime], float]) -> Timeseries:
            return Timeseries.from_values(
                start_date=parameters.temporal.start_date,
                frequency=parameters.temporal.timestep,
                values=[getter(time) for time in self._time_frame],
            )

        def state(var) -> Timeseries:
            return solution(lambda time: var.get_model_var(time).solution_value())

        power = solution(lambda time: dispatch.power_level_var.get_model_var(time).solution_value())
        if abs(power.min()) <= 1e-6 and abs(power.max()) <= 1e-6:
            cfg.logger.debug(
                f"*** Info *** The optimal solution for the unit {self.equipment.name} is such that "
                "the unit remains offline and delivers no power output."
            )

        return ThermalOptimisationResult(
            on_up=state(dispatch.on_up_var),
            on_down=state(dispatch.on_down_var),
            off=state(dispatch.off_var),
            start=state(dispatch.on_start_var) if dispatch.has_start else None,
            stop=state(dispatch.stop_var) if dispatch.has_stop else None,
            on_flat=state(dispatch.on_flat_var) if dispatch.has_flat else None,
        )

    def _var(self, prefix: str, time: DateTime) -> str:
        return f"{prefix}_{self.equipment.name}_{time}"

    def _add_contracted_difference_constraints(self, model: OptimisationModel, time: DateTime) -> None:
        """Bound each contracted difference below by ``procured - provided`` (it is null otherwise)."""
        reserves = self._reserves
        for prefix, procured, provided in (
            ("contracted_difference_up", reserves.reserves_up_procured, "reserves_up"),
            ("contracted_difference_down", reserves.reserves_down_procured, "reserves_down"),
            (
                "automated_contracted_difference_up",
                reserves.feasible_automated_reserves_up_procured,
                "automated_reserves_up",
            ),
            (
                "automated_contracted_difference_down",
                reserves.feasible_automated_reserves_down_procured,
                "automated_reserves_down",
            ),
        ):
            model.add_constraint(
                model.get_variable(self._var(prefix, time))
                >= procured.get_value(time) - model.get_variable(reserves.var(provided, time)),
                f"def_{prefix}_{self.equipment.name}_{time}",
            )

    def _reserve_forecasts(
        self, parameters: DayAheadOrdersParameters
    ) -> tuple[Timeseries, Timeseries, Timeseries, Timeseries, float]:
        """
        Collapse the unit's procured reserve forecasts into what the reserve handler needs.

        Manual reserves (mFRR + RR) are taken as procured. Automated ones (aFRR + FCR) are
        clipped to the unit's capacity: what fits becomes the feasible procurement, what
        does not is summed into a scalar penalised once in the objective.

        :return: ``(reserves_up, reserves_down, feasible_automated_up,
            feasible_automated_down, automated_unsupplied)``
        :rtype: tuple[Timeseries, Timeseries, Timeseries, Timeseries, float]
        """
        unit = self.equipment
        temporal = parameters.temporal
        end = unit.additional_hours + temporal.end_date

        def forecast(source: ForecastingMatrix | LazyForecastingMatrix | None) -> Timeseries:
            if source is None:
                return Timeseries.from_index(temporal.start_date, temporal.timestep, end, 0)
            return source.get_forecast(temporal.execution_date, temporal.start_date, end)

        maximum_afrr = unit.maximum_afrr if unit.maximum_afrr is not None else 0.0
        maximum_fcr = unit.maximum_fcr if unit.maximum_fcr is not None else 0.0

        reserves_up = forecast(unit.mfrr_up_procured) + forecast(unit.rr_up_procured)
        reserves_down = forecast(unit.mfrr_down_procured) + forecast(unit.rr_down_procured)

        afrr_up = forecast(unit.afrr_up_procured).filter(self._time_frame, inplace=False)
        afrr_down = forecast(unit.afrr_down_procured).filter(self._time_frame, inplace=False)
        fcr_up = forecast(unit.fcr_up_procured).filter(self._time_frame, inplace=False)
        fcr_down = forecast(unit.fcr_down_procured).filter(self._time_frame, inplace=False)

        feasible_automated_up = afrr_up.clip(upper_bound=maximum_afrr, inplace=False) + fcr_up.clip(
            upper_bound=maximum_fcr, inplace=False
        )
        feasible_automated_down = afrr_down.clip(upper_bound=maximum_afrr, inplace=False) + fcr_down.clip(
            upper_bound=maximum_fcr, inplace=False
        )

        automated_unsupplied = (
            (afrr_up - maximum_afrr).clip(lower_bound=0, inplace=False)
            + (fcr_up - maximum_fcr).clip(lower_bound=0, inplace=False)
            + (afrr_down - maximum_afrr).clip(lower_bound=0, inplace=False)
            + (fcr_down - maximum_fcr).clip(lower_bound=0, inplace=False)
        ).sum()

        cfg.logger.debug(f"automated unsupplied reserves : {automated_unsupplied}")
        return reserves_up, reserves_down, feasible_automated_up, feasible_automated_down, automated_unsupplied


def solve_thermal_unit(
    unit: ThermalDAO,
    parameters: DayAheadOrdersParameters,
    price_type: str,
) -> ThermalOptimisationResult:
    """
    Build and solve the day-ahead bidding model of a single thermal unit.

    :param unit: Thermal unit to optimise
    :type unit: ThermalDAO
    :param parameters: Optimisation parameters
    :type parameters: DayAheadOrdersParameters
    :param price_type: Name of the price forecast scenario, e.g. ``"Medium"``
    :type price_type: str
    :return: Solved states of the unit
    :rtype: ThermalOptimisationResult
    """
    model = OptimisationModel(
        solver_name=parameters.solver.solver_name,
        name=f"Optimization program for thermal unit {unit.name}",
        options=SolverOptions(
            presolve=parameters.solver.use_presolve,
            duality_gap=parameters.solver.duality_gap,
            time_limit=parameters.solver.timeout,
        ),
    )
    model.set_direction("maximize")

    step = ThermalDAOStep(unit, _price_forecast(unit, parameters, price_type))
    step.add_variables(model, parameters)
    step.add_constraints(model, parameters)
    step.add_objective(model, parameters)

    if parameters.solver.export_lp:
        lp_dir = parameters.get_lp_dir()
        lp_dir.mkdir(parents=True, exist_ok=True)
        model.export_model(str(lp_dir / f"{unit.name}_price_{price_type}.lp"))

    cfg.logger.info(f"Optimisation model '{model.name}' with price type '{price_type}'")
    model.solve()

    return step.extract_result(parameters)


def build_dispatch_state_sequence(
    result: ThermalOptimisationResult, parameters: DayAheadOrdersParameters
) -> Timeseries:
    """
    Encode the solved states of a unit into the sequence stored on the equipment.

    Unlike the sequence used for order formulation, this one keeps the regimes distinct —
    downstream modules need to know whether the unit was ramping up, ramping down or flat.
    It uses :class:`~atlas.enums.ThermalDispatchState`.

    The state indicators are mutually exclusive; the first one set wins, and a timestep
    with no indicator set is reported as :attr:`~atlas.enums.ThermalDispatchState.UNKNOWN`.

    :param result: Solved states of the unit for one price scenario
    :type result: ThermalOptimisationResult
    :param parameters: Module parameters, used for the timezone of the index
    :type parameters: DayAheadOrdersParameters
    :return: State sequence over the unit's horizon
    :rtype: Timeseries
    """
    indicators: list[tuple[ThermalDispatchState, Timeseries | None]] = [
        (ThermalDispatchState.ON_UP, result.on_up),
        (ThermalDispatchState.ON_DOWN, result.on_down),
        (ThermalDispatchState.OFF, result.off),
        (ThermalDispatchState.START, result.start),
        (ThermalDispatchState.STOP, result.stop),
        (ThermalDispatchState.ON_FLAT, result.on_flat),
    ]

    index = list(result.off.index)
    values = [
        float(
            next(
                (state for state, series in indicators if series is not None and series.get_value(time) == 1),
                ThermalDispatchState.UNKNOWN,
            )
        )
        for time in index
    ]

    return Timeseries(
        pl.DataFrame(
            {"time": index, "value": values},
            schema={"time": pl.Datetime("us", parameters.temporal.start_date.timezone_name), "value": pl.Float64()},
        )
    )


def _price_forecast(unit: ThermalDAO, parameters: DayAheadOrdersParameters, price_type: str) -> Timeseries:
    """Price forecast of the unit's market area for the *price_type* scenario, over its horizon."""
    attribute = f"price_forecast_{price_type.lower()}"
    forecast = getattr(unit.portfolio.market_area, attribute)
    if forecast is None:
        raise AttributeError(f"{unit.portfolio.market_area.name} has no attribute '{attribute}'")
    return forecast.get_forecast(
        parameters.temporal.execution_date,
        parameters.temporal.start_date,
        parameters.temporal.end_date + unit.additional_hours,
    )
