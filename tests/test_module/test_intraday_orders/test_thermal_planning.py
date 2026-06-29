"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for compute_planning_delta and build_order_windows.

These functions encode the core thermal bidding logic:
  - compute_planning_delta: classify each timestep as startup / shutdown / modulation / no change
  - build_order_windows: group consecutive timesteps into labelled windows that drive order creation

Test design
-----------
The order window spans T0–T4 (5 hours).  Window scenarios use T2 (the middle timestep)
so that t_before=T1 and t_after=T3 are always inside the cleared_position timeseries
(which only covers [start_date, penultimate_date]).
"""

import pendulum

from atlas.enums import ThermalStrategy
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_orders.input_objects.thermal import ThermalIDO
from atlas.modules.intraday_orders.models.enums import PlanningDelta, WindowType
from atlas.modules.intraday_orders.orders_formulation.thermal import build_order_windows, compute_planning_delta
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.timing import generate_datetimes

from .conftest import EXEC_DATE, const_ts, make_fm, make_node, make_portfolio

# ---------------------------------------------------------------------------
# Time constants
# ---------------------------------------------------------------------------

START = pendulum.datetime(2028, 1, 1, 0, 0, 0)
END = pendulum.datetime(2028, 1, 1, 5, 0, 0)
STEP = pendulum.duration(hours=1)

T0 = START
T1 = START.add(hours=1)
T2 = START.add(hours=2)  # window scenarios are centred here
T3 = START.add(hours=3)
T4 = START.add(hours=4)  # penultimate = END - STEP

PMIN = 30.0
PMAX = 100.0

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _params() -> IntradayOrdersParameters:
    return IntradayOrdersParameters.model_validate(
        {
            "temporal": {
                "start_date": str(START),
                "execution_date": str(EXEC_DATE),
                "end_date": str(END),
                "timestep": "PT1H",
            }
        }
    )


def _make_thermal(da_values: dict, new_plan_values: dict, pmin: float = PMIN) -> ThermalIDO:
    """Build a minimal ThermalIDO.

    da_values: {DateTime: float} for cleared DA engagement (covers extended range for t_before/t_after)
    new_plan_values: {DateTime: float} for the new intraday planning
    """
    ext_start = START.subtract(hours=1)
    ext_end = END.add(hours=1)

    da_ts = const_ts(0.0, ext_start, STEP, ext_end)
    for t, v in da_values.items():
        da_ts.set_value(t, v)

    plan_ts = const_ts(0.0, START, STEP, END)
    for t, v in new_plan_values.items():
        plan_ts.set_value(t, v)

    return ThermalIDO(
        name="unit",
        strategy=ThermalStrategy.BASE,
        node=make_node(),
        portfolio=make_portfolio(),
        da_cleared_quantity=da_ts,
        id_po_for_orders=make_fm(plan_ts),
        minimum_power=const_ts(pmin, ext_start, STEP, ext_end),
        maximum_power=const_ts(PMAX, ext_start, STEP, ext_end),
        startup_cost=const_ts(10.0, START, STEP, END),
        variable_cost=const_ts(10.0, START, STEP, END),
    )


def _planning_delta_ts(code: PlanningDelta, at: pendulum.DateTime) -> Timeseries:
    params = _params()
    ts = Timeseries.from_index(START, STEP, params.penultimate_date, 0.0)
    ts.set_value(at, code)
    return ts


# ---------------------------------------------------------------------------
# compute_planning_delta
# ---------------------------------------------------------------------------


class TestComputePlanningDelta:
    """Each test verifies one PlanningDelta code classification at T2."""

    def _delta_at(self, da_values: dict, new_plan_values: dict) -> int:
        params = _params()
        thermal = _make_thermal(da_values, new_plan_values)
        timestamps = generate_datetimes(START, params.penultimate_date, STEP)
        result = compute_planning_delta(thermal, timestamps, params)
        return int(result.get_value(T2))

    def test_modulation_up(self):
        # Both above Pmin, new > previous → MODULATION_UP
        assert self._delta_at({T2: 50.0}, {T2: 80.0}) == PlanningDelta.MODULATION_UP

    def test_modulation_down(self):
        # Both above Pmin, new < previous → MODULATION_DOWN
        assert self._delta_at({T2: 80.0}, {T2: 50.0}) == PlanningDelta.MODULATION_DOWN

    def test_startup(self):
        # Previous below Pmin, new above Pmin → STARTUP
        assert self._delta_at({T2: 0.0}, {T2: 80.0}) == PlanningDelta.STARTUP

    def test_shutdown(self):
        # Previous above Pmin, new below Pmin → SHUTDOWN
        assert self._delta_at({T2: 80.0}, {T2: 0.0}) == PlanningDelta.SHUTDOWN

    def test_no_change_equal_power(self):
        assert self._delta_at({T2: 80.0}, {T2: 80.0}) == PlanningDelta.NO_CHANGE

    def test_no_change_both_below_pmin(self):
        # Neither planning reaches Pmin → no actionable change
        assert self._delta_at({T2: 5.0}, {T2: 15.0}) == PlanningDelta.NO_CHANGE


# ---------------------------------------------------------------------------
# build_order_windows
# ---------------------------------------------------------------------------


class TestBuildOrderWindows:
    """Each test verifies one WindowType using a single-timestep window at T2.

    was_running_before = cleared_position[T1] >= Pmin
    is_running_after   = cleared_position[T3] >= Pmin
    """

    def _run(self, code: PlanningDelta, da_t1: float, da_t3: float) -> list:
        params = _params()
        thermal = _make_thermal(da_values={T1: da_t1, T3: da_t3}, new_plan_values={T2: 80.0})
        delta = _planning_delta_ts(code, T2)
        orders_time = generate_datetimes(START, params.penultimate_date, STEP)
        return build_order_windows(thermal, delta, orders_time, params)

    # ---- STARTUP scenarios ------------------------------------------------

    def test_bridge_up(self):
        # STARTUP + was_running_before + is_running_after → bridging a gap between two running phases
        windows = self._run(PlanningDelta.STARTUP, da_t1=80.0, da_t3=80.0)
        assert len(windows) == 1
        assert windows[0].window_type == WindowType.BRIDGE_UP

    def test_extended_end(self):
        # STARTUP + was_running_before + NOT is_running_after → extending existing run at its end
        windows = self._run(PlanningDelta.STARTUP, da_t1=80.0, da_t3=0.0)
        assert len(windows) == 1
        assert windows[0].window_type == WindowType.EXTENDED_END

    def test_extended_beginning(self):
        # STARTUP + NOT was_running_before + is_running_after → extending existing run at its start
        windows = self._run(PlanningDelta.STARTUP, da_t1=0.0, da_t3=80.0)
        assert len(windows) == 1
        assert windows[0].window_type == WindowType.EXTENDED_BEGINNING

    def test_new_start(self):
        # STARTUP + NOT was_running_before + NOT is_running_after → brand-new isolated startup
        windows = self._run(PlanningDelta.STARTUP, da_t1=0.0, da_t3=0.0)
        assert len(windows) == 1
        assert windows[0].window_type == WindowType.NEW_START

    # ---- SHUTDOWN scenarios -----------------------------------------------

    def test_new_stop(self):
        # SHUTDOWN + was_running_before + is_running_after → inserting a stop inside a running phase
        windows = self._run(PlanningDelta.SHUTDOWN, da_t1=80.0, da_t3=80.0)
        assert len(windows) == 1
        assert windows[0].window_type == WindowType.NEW_STOP

    def test_shortened_end(self):
        # SHUTDOWN + was_running_before + NOT is_running_after → trimming the end of a running phase
        windows = self._run(PlanningDelta.SHUTDOWN, da_t1=80.0, da_t3=0.0)
        assert len(windows) == 1
        assert windows[0].window_type == WindowType.SHORTENED_END

    def test_shortened_beginning(self):
        # SHUTDOWN + NOT was_running_before + is_running_after → trimming the start of a running phase
        windows = self._run(PlanningDelta.SHUTDOWN, da_t1=0.0, da_t3=80.0)
        assert len(windows) == 1
        assert windows[0].window_type == WindowType.SHORTENED_BEGINNING

    def test_bridge_down(self):
        # SHUTDOWN + NOT was_running_before + NOT is_running_after → removing an isolated startup
        windows = self._run(PlanningDelta.SHUTDOWN, da_t1=0.0, da_t3=0.0)
        assert len(windows) == 1
        assert windows[0].window_type == WindowType.BRIDGE_DOWN

    # ---- MODULATION scenarios (context irrelevant) ------------------------

    def test_modulation_up(self):
        windows = self._run(PlanningDelta.MODULATION_UP, da_t1=80.0, da_t3=80.0)
        assert len(windows) == 1
        assert windows[0].window_type == WindowType.MODULATION_UP

    def test_modulation_down(self):
        windows = self._run(PlanningDelta.MODULATION_DOWN, da_t1=80.0, da_t3=80.0)
        assert len(windows) == 1
        assert windows[0].window_type == WindowType.MODULATION_DOWN

    # ---- NO_CHANGE → no window produced -----------------------------------

    def test_no_change_produces_no_window(self):
        params = _params()
        thermal = _make_thermal(da_values={}, new_plan_values={})
        delta = Timeseries.from_index(START, STEP, params.penultimate_date, PlanningDelta.NO_CHANGE)
        orders_time = generate_datetimes(START, params.penultimate_date, STEP)
        windows = build_order_windows(thermal, delta, orders_time, params)
        assert windows == []

    def test_consecutive_timestamps_form_one_window(self):
        # Two consecutive STARTUP codes → grouped into a single window
        params = _params()
        thermal = _make_thermal(da_values={T1: 0.0, T4: 0.0}, new_plan_values={T2: 80.0, T3: 80.0})
        delta = Timeseries.from_index(START, STEP, params.penultimate_date, 0.0)
        delta.set_value(T2, PlanningDelta.STARTUP)
        delta.set_value(T3, PlanningDelta.STARTUP)
        orders_time = generate_datetimes(START, params.penultimate_date, STEP)
        windows = build_order_windows(thermal, delta, orders_time, params)
        assert len(windows) == 1
        assert len(windows[0].index) == 2
