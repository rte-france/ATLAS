"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum

from atlas import ForecastingMatrix, Timeseries
from atlas.enums import CouplingType
from atlas.modules.balancing_market_bsp_orders.order_formulators.thermal import StartupCase, ThermalOrderFormulator


def _make_formulator(equipment, time_index, parameters) -> ThermalOrderFormulator:
    return ThermalOrderFormulator(equipment, time_index, parameters)


def _set_power_pattern(equipment, parameters, overrides, default=0.0):
    """Rebuilds equipment.power as a full-range ForecastingMatrix (covering all of
    parameters.temporal, since formulate()/the formulator's own helpers always read
    over that full window) with a constant baseline, specific timesteps overridden.
    """
    ts = Timeseries.from_index(
        start_date=parameters.temporal.start_date,
        frequency=parameters.temporal.timestep,
        end_date=parameters.temporal.end_date,
        default_value=default,
    )
    for dt, value in overrides.items():
        ts.set_value(dt, value)

    fm = ForecastingMatrix()
    fm.add(ts, parameters.temporal.execution_date)
    object.__setattr__(equipment, "power", fm)


def _forecasted_power(equipment, parameters):
    """Same slicing formulate() itself uses, for calling _classify_startup_case directly."""
    start = parameters.temporal.start_date
    end = parameters.temporal.end_date - parameters.temporal.timestep
    return equipment.power.get_forecast(parameters.temporal.execution_date, start, end)


class TestClassifyStartupCase:
    def test_full_startup_when_off_on_both_sides(self, thermal_equipment, parameters):
        """previous=0, current=0, next=0 (the default 0.0 baseline everywhere) -> FULL_STARTUP."""
        _set_power_pattern(thermal_equipment, parameters, {})
        test_time = parameters.temporal.start_date.add(minutes=15)

        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        forecasted_power = _forecasted_power(thermal_equipment, parameters)
        assert formulator._classify_startup_case(forecasted_power, test_time) == StartupCase.FULL_STARTUP

    def test_on_both_sides_when_on_before_and_after(self, thermal_equipment, parameters):
        """previous=50, current=0, next=50 -> ON_BOTH_SIDES."""
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(
            thermal_equipment,
            parameters,
            {test_time.subtract(minutes=15): 50.0, test_time.add(minutes=15): 50.0},
        )

        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        forecasted_power = _forecasted_power(thermal_equipment, parameters)
        assert formulator._classify_startup_case(forecasted_power, test_time) == StartupCase.ON_BOTH_SIDES

    def test_on_before_only_when_on_before_and_off_after(self, thermal_equipment, parameters):
        """previous=50, current=0, next=0 -> ON_BEFORE_ONLY."""
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(thermal_equipment, parameters, {test_time.subtract(minutes=15): 50.0})

        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        forecasted_power = _forecasted_power(thermal_equipment, parameters)
        assert formulator._classify_startup_case(forecasted_power, test_time) == StartupCase.ON_BEFORE_ONLY

    def test_on_after_only_when_off_before_and_on_after(self, thermal_equipment, parameters):
        """previous=0, current=0, next=50 -> ON_AFTER_ONLY."""
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(thermal_equipment, parameters, {test_time.add(minutes=15): 50.0})

        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        forecasted_power = _forecasted_power(thermal_equipment, parameters)
        assert formulator._classify_startup_case(forecasted_power, test_time) == StartupCase.ON_AFTER_ONLY

    def test_no_startup_when_power_is_nonzero(self, thermal_equipment, parameters):
        """current=30 (!= 0) -> NO_STARTUP, regardless of neighbors."""
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(thermal_equipment, parameters, {test_time: 30.0})

        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        forecasted_power = _forecasted_power(thermal_equipment, parameters)
        assert formulator._classify_startup_case(forecasted_power, test_time) == StartupCase.NO_STARTUP

    def test_no_startup_when_minimum_power_not_positive(self, thermal_equipment, parameters):
        """current=0 but minimum_power(t)=0 -> NO_STARTUP (a unit with no floor
        can't be said to be 'starting up').
        """
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(thermal_equipment, parameters, {})
        min_power_ts = Timeseries.from_index(
            start_date=parameters.temporal.start_date,
            frequency=parameters.temporal.timestep,
            end_date=parameters.temporal.end_date,
            default_value=20.0,
        )
        min_power_ts.set_value(test_time, 0.0)
        object.__setattr__(thermal_equipment, "minimum_power", min_power_ts)

        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        forecasted_power = _forecasted_power(thermal_equipment, parameters)
        assert formulator._classify_startup_case(forecasted_power, test_time) == StartupCase.NO_STARTUP


class TestCheckOnOffTimeRequirement:
    def test_trivially_satisfied_when_duration_requirement_is_zero(self, thermal_equipment, parameters):
        """minimum_time_on defaults to 0 -> always satisfied, whatever the power pattern."""
        test_time = parameters.temporal.start_date.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._check_on_off_time_requirement(test_time, searching_on=True, searching_backwards=True)
        assert formulator._check_on_off_time_requirement(test_time, searching_on=True, searching_backwards=False)

    def test_minimum_time_on_satisfied_when_on_long_enough(self, thermal_equipment, parameters):
        """Default fixture is a constant 50 (on) across the whole window; with
        minimum_time_on=15min, looking backward from 00:30 finds >= 15 min of
        uninterrupted 'on' history before it.
        """
        object.__setattr__(thermal_equipment, "minimum_time_on", pendulum.duration(minutes=15))
        test_time = parameters.temporal.start_date.add(minutes=30)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._check_on_off_time_requirement(test_time, searching_on=True, searching_backwards=True)

    def test_minimum_time_on_not_satisfied_when_turned_on_recently(self, thermal_equipment, parameters):
        """Equipment turned on at 00:15 (00:00 is off), only 15 min before the 00:30
        test point -> short of the 30 min minimum_time_on requirement.
        """
        object.__setattr__(thermal_equipment, "minimum_time_on", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=30)
        _set_power_pattern(thermal_equipment, parameters, {test_time.subtract(minutes=15): 50.0}, default=0.0)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert not formulator._check_on_off_time_requirement(test_time, searching_on=True, searching_backwards=True)

    def test_minimum_time_off_satisfied_forward(self, thermal_equipment, parameters):
        """Equipment goes off at 00:15 and stays off until 00:30 (>= 20 min minimum_time_off)."""
        object.__setattr__(thermal_equipment, "minimum_time_off", pendulum.duration(minutes=20))
        test_time = parameters.temporal.start_date
        _set_power_pattern(thermal_equipment, parameters, {test_time.add(minutes=30): 50.0}, default=0.0)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._check_on_off_time_requirement(test_time, searching_on=False, searching_backwards=False)


class TestCase5FullStartup:
    def test_splits_into_indivisible_and_divisible_orders(self, thermal_equipment, parameters):
        """start1 (indivisible, up to minimum_power=20): price = variable_cost(80) +
        startup_cost(500) / (20 * duration_hours(0.25)) = 80 + 100 = 180.
        start2 (divisible, minimum_power to maximum_power = 100-20=80): price =
        variable_cost = 80. Linked by a single PARENT_CHILDREN coupling.
        """
        test_time = parameters.temporal.start_date.add(minutes=15)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        orders, couplings = formulator._formulate_case_5_orders(test_time, next_time)

        assert len(orders) == 2
        start1, start2 = orders
        assert start1.qmin == start1.qmax == 20
        assert start1.price == 180
        assert "_start1" in start1.name
        assert start2.qmin == 0
        assert start2.qmax == 80
        assert start2.price == 80
        assert "_start2" in start2.name

        assert len(couplings) == 1
        assert couplings[0].coupling_type == CouplingType.PARENT_CHILDREN
        assert couplings[0].orders == [start1, start2]
        assert couplings[0].name == f"parent_children1_{start1.name}"

    def test_no_startup_when_startup_duration_not_elapsed(self, thermal_equipment, parameters):
        """startup_duration (30min) > time elapsed since execution_date (15min) -> invalid."""
        object.__setattr__(thermal_equipment, "startup_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.execution_date.add(minutes=15)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        orders, couplings = formulator._formulate_case_5_orders(test_time, next_time)
        assert orders == []
        assert couplings == []

    def test_no_startup_when_minimum_stable_power_duration_invalidates(self, thermal_equipment, parameters):
        """minimum_stable_power_duration (30min) > timestep (15min), and the
        equipment's power changed just 15 min before test_time (50 -> 30) -> not
        stable long enough -> the gate invalidates the startup.
        """
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=30)
        _set_power_pattern(thermal_equipment, parameters, {test_time.subtract(minutes=15): 30.0}, default=50.0)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        orders, couplings = formulator._formulate_case_5_orders(test_time, next_time)
        assert orders == []
        assert couplings == []


class TestCase1OnBothSides:
    def test_bounded_order_without_gradient(self, thermal_equipment, parameters):
        """maximum_gradient=0 -> bounded_qmax=maximum_power=100, bounded_qmin=minimum_power=20.
        price = variable_cost(80) - startup_cost(500)/(100*0.25) = 80 - 20 = 60.
        """
        test_time = parameters.temporal.start_date.add(minutes=15)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        order = formulator._formulate_case_1_order(test_time, next_time)
        assert order is not None
        assert order.qmax == 100
        assert order.qmin == 20
        assert order.price == 60

    def test_bounded_order_with_gradient(self, thermal_equipment, parameters):
        """maximum_gradient=2 MW/min -> max_grad = 2*15 = 30. previous=40, next=60
        (next >= previous): bounded_qmax=min(100,40+30)=70, bounded_qmin=max(20,60-30)=30.
        price = 80 - 500/(70*0.25) = 80 - 28.57 = 51.43.
        """
        object.__setattr__(thermal_equipment, "maximum_gradient", 2.0)
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(
            thermal_equipment,
            parameters,
            {test_time.subtract(minutes=15): 40.0, test_time.add(minutes=15): 60.0},
            default=50.0,
        )
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        order = formulator._formulate_case_1_order(test_time, next_time)
        assert order is not None
        assert order.qmax == 70
        assert order.qmin == 30
        assert order.price == 51.43

    def test_invalid_when_gradient_feasibility_exceeded(self, thermal_equipment, parameters):
        """Deviation from legacy (documented in thermal.py): the feasibility check
        uses maximum_gradient * timestep_minutes rather than legacy's hardcoded * 60.
        threshold = 2*(2*15) = 60; |next(70) - previous(0)| = 70 > 60 -> invalid.
        """
        object.__setattr__(thermal_equipment, "maximum_gradient", 2.0)
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(
            thermal_equipment,
            parameters,
            {test_time.subtract(minutes=15): 0.0, test_time.add(minutes=15): 70.0},
            default=50.0,
        )
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._formulate_case_1_order(test_time, next_time) is None


class TestCase2OnBeforeOnly:
    def test_bounded_order_around_previous_power(self, thermal_equipment, parameters):
        """gradient disabled -> bounded_qmax=maximum_power=100. previous_power=50
        (the default constant fixture) -> bounded_qmin=max(20,50)=50.
        """
        test_time = parameters.temporal.start_date.add(minutes=15)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        order = formulator._formulate_case_2_order(test_time, next_time)
        assert order is not None
        assert order.qmax == 100
        assert order.qmin == 50
        assert order.price == 80

    def test_invalid_when_minimum_time_off_not_satisfied(self, thermal_equipment, parameters):
        """The default fixture never actually goes to 0 going forward from
        test_time, so the MinimumTimeOff-forward check fails immediately.
        """
        object.__setattr__(thermal_equipment, "minimum_time_off", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=15)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._formulate_case_2_order(test_time, next_time) is None


class TestCase3OnAfterOnly:
    def test_bounded_order_around_next_power(self, thermal_equipment, parameters):
        """gradient disabled -> bounded_qmax=maximum_power=100. next_power=50
        (the default constant fixture) -> bounded_qmin=max(20,50)=50.
        """
        test_time = parameters.temporal.start_date.add(minutes=15)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        order = formulator._formulate_case_3_order(test_time, next_time)
        assert order is not None
        assert order.qmax == 100
        assert order.qmin == 50
        assert order.price == 80

    def test_invalid_when_startup_duration_not_elapsed(self, thermal_equipment, parameters):
        """startup_duration (30min) > time elapsed since execution_date (15min) -> invalid."""
        object.__setattr__(thermal_equipment, "startup_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.execution_date.add(minutes=15)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._formulate_case_3_order(test_time, next_time) is None

    def test_invalid_when_minimum_time_off_not_satisfied(self, thermal_equipment, parameters):
        """The default fixture never actually goes to 0 going backward from
        test_time, so the MinimumTimeOff-backward check fails immediately.
        """
        object.__setattr__(thermal_equipment, "minimum_time_off", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=15)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._formulate_case_3_order(test_time, next_time) is None
