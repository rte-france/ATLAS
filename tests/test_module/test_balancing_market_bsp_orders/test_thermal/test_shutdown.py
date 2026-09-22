"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
import pendulum

from atlas import ForecastingMatrix, Timeseries
from atlas.enums import CouplingType, OrderType
from atlas.modules.balancing_market_bsp_orders.order_formulators.thermal import ThermalOrderFormulator


def _make_formulator(equipment, time_index, parameters) -> ThermalOrderFormulator:
    return ThermalOrderFormulator(equipment, time_index, parameters)


def _set_power_pattern(equipment, parameters, overrides, default=0.0):
    """Rebuilds equipment.power as a full-range ForecastingMatrix, specific
    timesteps overridden; points outside [start_date, end_date] default to 0.0.
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


def _ts(parameters, value):
    return Timeseries.from_index(
        start_date=parameters.temporal.start_date,
        frequency=parameters.temporal.timestep,
        end_date=parameters.temporal.end_date,
        default_value=value,
    )


class TestIsShutdownEligible:
    def test_eligible_when_running_above_minimum_with_no_procured(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._is_shutdown_eligible(
            test_time, _ts(parameters, 50.0), _ts(parameters, 20.0), _ts(parameters, 0.0), _ts(parameters, 0.0)
        )

    def test_not_eligible_when_below_minimum_power(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert not formulator._is_shutdown_eligible(
            test_time, _ts(parameters, 15.0), _ts(parameters, 20.0), _ts(parameters, 0.0), _ts(parameters, 0.0)
        )

    def test_not_eligible_when_minimum_power_not_positive(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert not formulator._is_shutdown_eligible(
            test_time, _ts(parameters, 50.0), _ts(parameters, 0.0), _ts(parameters, 0.0), _ts(parameters, 0.0)
        )

    def test_not_eligible_with_upward_procured(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert not formulator._is_shutdown_eligible(
            test_time, _ts(parameters, 50.0), _ts(parameters, 20.0), _ts(parameters, 5.0), _ts(parameters, 0.0)
        )

    def test_not_eligible_with_downward_procured(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert not formulator._is_shutdown_eligible(
            test_time, _ts(parameters, 50.0), _ts(parameters, 20.0), _ts(parameters, 0.0), _ts(parameters, 5.0)
        )


class TestClassifyShutdownCase:
    def test_case_1_when_off_both_sides(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(thermal_equipment, parameters, {}, default=0.0)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._classify_shutdown_case(test_time) == "case_1"

    def test_case_2_when_off_before_only(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(thermal_equipment, parameters, {test_time.add(minutes=15): 50.0}, default=0.0)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._classify_shutdown_case(test_time) == "case_2"

    def test_case_3_when_off_after_only(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(thermal_equipment, parameters, {test_time.subtract(minutes=15): 50.0}, default=0.0)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._classify_shutdown_case(test_time) == "case_3"

    def test_case_4_when_on_both_sides(self, thermal_equipment, parameters):
        """Default fixture (constant 50) -> on both sides."""
        test_time = parameters.temporal.start_date.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._classify_shutdown_case(test_time) == "case_4"


class TestStartupFitsWithinTimestep:
    def test_fits_when_sum_at_or_below_timestep(self, thermal_equipment, parameters):
        object.__setattr__(thermal_equipment, "startup_duration", pendulum.duration(minutes=10))
        object.__setattr__(thermal_equipment, "setup_delay", 0.0)
        formulator = _make_formulator(thermal_equipment, [parameters.temporal.start_date], parameters)

        assert formulator._startup_fits_within_timestep()

    def test_does_not_fit_when_sum_exceeds_timestep(self, thermal_equipment, parameters):
        object.__setattr__(thermal_equipment, "startup_duration", pendulum.duration(minutes=20))
        formulator = _make_formulator(thermal_equipment, [parameters.temporal.start_date], parameters)

        assert not formulator._startup_fits_within_timestep()


class TestShutdownMinimumStablePowerDurationGate:
    def test_passes_when_duration_shorter_than_timestep(self, thermal_equipment, parameters):
        """minimum_stable_power_duration defaults to 0 -> no-op, always True."""
        test_time = parameters.temporal.start_date.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._shutdown_min_stable_power_duration_gate(test_time) is True

    def test_always_passes_at_exact_timestep_boundary(self, thermal_equipment, parameters):
        """MSPD == timestep exactly: the before/after stability checks are
        structurally guaranteed to pass at this boundary (elapsed already
        reaches the duration requirement after a single look-back step,
        whatever value is found there) -> always True, even with a power
        pattern that changes right next to test_time.
        """
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=15))
        test_time = parameters.temporal.start_date.add(minutes=30)
        _set_power_pattern(
            thermal_equipment,
            parameters,
            {test_time.subtract(minutes=15): 10.0, test_time.add(minutes=15): 90.0},
            default=50.0,
        )
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._shutdown_min_stable_power_duration_gate(test_time) is True

    def test_always_fails_when_duration_exceeds_timestep(self, thermal_equipment, parameters):
        """MSPD (30min) > timestep, equipment genuinely stable on both sides
        (default constant fixture) -> still always False for Shutdown: the
        plateau-extension block never matches order_type 'Shutdown' in any
        branch, independent of actual stability.
        """
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=30)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._shutdown_min_stable_power_duration_gate(test_time) is False


class TestBuildShutdownOrder:
    def test_uses_s_direction_segment(self, thermal_equipment, parameters):
        """Distinct from build_order's 'u'/'d' — a shutdown is a Buy order but named 's'."""
        test_time = parameters.temporal.start_date
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        order = formulator._build_shutdown_order(test_time, next_time, price=80.0, qmax=50.0)
        assert order is not None
        assert "_s_" in order.name
        assert order.qmin == order.qmax == 50
        assert order.order_type == OrderType.Buy

    def test_returns_none_when_qmax_rounds_to_zero(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        assert formulator._build_shutdown_order(test_time, next_time, price=80.0, qmax=0.4) is None


class TestFormulateShutdownOrder:
    def test_case_1_cancels_startup_cost(self, thermal_equipment, parameters):
        """off both sides -> price = 80 - 500/(50*0.25) = 40."""
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(
            thermal_equipment,
            parameters,
            {test_time.subtract(minutes=15): 0.0, test_time.add(minutes=15): 0.0},
            default=50.0,
        )
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        next_time = test_time.add(minutes=15)

        order, _ = formulator._formulate_shutdown_order(test_time, next_time)
        assert order is not None
        assert order.qmax == 50
        assert order.price == 40

    def test_case_2_off_before_only_no_shutdown_cost(self, thermal_equipment, parameters):
        """off before only, trivial MinimumTimeOn(0) -> price = variable_cost = 80."""
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(thermal_equipment, parameters, {test_time.subtract(minutes=15): 0.0}, default=50.0)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        next_time = test_time.add(minutes=15)

        order, _ = formulator._formulate_shutdown_order(test_time, next_time)
        assert order is not None
        assert order.price == 80

    def test_case_3_off_after_only_no_shutdown_cost(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(thermal_equipment, parameters, {test_time.add(minutes=15): 0.0}, default=50.0)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        next_time = test_time.add(minutes=15)

        order, _ = formulator._formulate_shutdown_order(test_time, next_time)
        assert order is not None
        assert order.price == 80

    def test_case_4_on_both_sides_includes_shutdown_cost(self, thermal_equipment, parameters):
        """on both sides (default fixture) -> price = 80 + 500/(50*0.25) = 120."""
        test_time = parameters.temporal.start_date.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        next_time = test_time.add(minutes=15)

        order, _ = formulator._formulate_shutdown_order(test_time, next_time)
        assert order is not None
        assert order.price == 120

    def test_case_4_invalid_when_minimum_time_off_exceeds_timestep(self, thermal_equipment, parameters):
        object.__setattr__(thermal_equipment, "minimum_time_off", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        next_time = test_time.add(minutes=15)

        order, _ = formulator._formulate_shutdown_order(test_time, next_time)
        assert order is None

    def test_case_4_invalid_when_restart_does_not_fit_within_timestep(self, thermal_equipment, parameters):
        object.__setattr__(thermal_equipment, "startup_duration", pendulum.duration(minutes=20))
        test_time = parameters.temporal.start_date.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        next_time = test_time.add(minutes=15)

        order, _ = formulator._formulate_shutdown_order(test_time, next_time)
        assert order is None

    def test_invalid_when_minimum_stable_power_duration_exceeds_timestep(self, thermal_equipment, parameters):
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        next_time = test_time.add(minutes=15)

        order, _ = formulator._formulate_shutdown_order(test_time, next_time)
        assert order is None

    def test_exclusion_coupling_to_adjacent_upward_order_when_gradient_enabled(self, thermal_equipment, parameters):
        object.__setattr__(thermal_equipment, "maximum_gradient", 2.0)
        test_time = parameters.temporal.start_date.add(minutes=15)
        previous_time = test_time.subtract(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        next_time = test_time.add(minutes=15)

        previous_order = formulator.build_order(
            order_type=OrderType.Sell, start=previous_time, end=test_time, price=10.0, qmin=0.0, qmax=10.0
        )
        formulator._record_upward_order(previous_time, previous_order)

        order, couplings = formulator._formulate_shutdown_order(test_time, next_time)
        assert order is not None
        assert any(
            c.coupling_type == CouplingType.EXCLUSION and previous_order in c.orders and order in c.orders
            for c in couplings
        )
