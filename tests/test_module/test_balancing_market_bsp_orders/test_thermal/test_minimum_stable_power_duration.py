"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
import pendulum

from atlas import ForecastingMatrix, Timeseries
from atlas.enums import OrderType
from atlas.modules.balancing_market_bsp_orders.order_formulators.thermal import ThermalOrderFormulator


def _make_formulator(equipment, time_index, parameters) -> ThermalOrderFormulator:
    return ThermalOrderFormulator(equipment, time_index, parameters)


def _set_power_pattern(equipment, parameters, overrides, default=0.0):
    """Rebuilds equipment.power as a full-range ForecastingMatrix, with specific
    timesteps overridden. Points outside [start_date, end_date] default to 0.0
    (via thermal.py's own _forecasted_power_at) — used below as an implicit
    'differs from the plateau' terminator.
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


class TestNoOpGuard:
    def test_passthrough_when_duration_shorter_than_timestep(self, thermal_equipment, parameters):
        """minimum_stable_power_duration (0) < timestep -> no-op, any power pattern."""
        test_time = parameters.temporal.start_date.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        result = formulator._apply_minimum_stable_power_duration_constraint(test_time, OrderType.Sell, 42.0)
        assert result == (42.0, True, False)


class TestStabilityChecks:
    def test_invalid_when_not_stable_before(self, thermal_equipment, parameters):
        """Power changes 15min before test_time (50->30), short of the 30min requirement -> invalid."""
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=30)
        _set_power_pattern(thermal_equipment, parameters, {test_time.subtract(minutes=15): 30.0}, default=50.0)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        result = formulator._apply_minimum_stable_power_duration_constraint(test_time, OrderType.Sell, 99.0)
        assert result == (0.0, False, False)

    def test_invalid_when_not_stable_after(self, thermal_equipment, parameters):
        """Power changes 15min after test_time (50->20), short of the 30min requirement -> invalid."""
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date
        _set_power_pattern(thermal_equipment, parameters, {test_time.add(minutes=30): 20.0}, default=50.0)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        result = formulator._apply_minimum_stable_power_duration_constraint(test_time, OrderType.Sell, 99.0)
        assert result == (0.0, False, False)

    def test_valid_passthrough_when_duration_equals_timestep_exactly(self, thermal_equipment, parameters):
        """MSPD == timestep exactly: neither guard fires (both are strict '<'), so
        once stability passes the quantity is returned unchanged. Same boundary
        _shutdown_min_stable_power_duration_gate initially got wrong.
        """
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=15))
        test_time = parameters.temporal.start_date.add(minutes=30)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        result = formulator._apply_minimum_stable_power_duration_constraint(test_time, OrderType.Sell, 77.0)
        assert result == (77.0, True, False)


class TestPlateauExtension:
    def test_ramp_guard_invalidates_when_both_neighbors_differ(self, thermal_equipment, parameters):
        """previous(80) and next(60) both differ from current(20) -> a ramp ->
        always invalid. Why Case 1 can never survive MSPD > timestep.
        """
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=30)
        _set_power_pattern(
            thermal_equipment,
            parameters,
            {test_time: 20.0, test_time.add(minutes=15): 60.0, test_time.add(minutes=30): 60.0},
            default=80.0,
        )
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        result = formulator._apply_minimum_stable_power_duration_constraint(test_time, OrderType.Sell, 99.0)
        assert result == (0.0, False, False)

    def test_extends_toward_previous_stable_level_for_matching_order_type(self, thermal_equipment, parameters):
        """next == current (no ramp guard); delta = previous(50) - current(20) = 30 -> Sell valid, undivisible."""
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=30)
        _set_power_pattern(
            thermal_equipment,
            parameters,
            {test_time: 20.0, test_time.add(minutes=15): 20.0, test_time.add(minutes=30): 20.0},
            default=50.0,
        )
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        result = formulator._apply_minimum_stable_power_duration_constraint(test_time, OrderType.Sell, 99.0)
        assert result == (30.0, True, True)

    def test_extension_toward_previous_invalid_for_mismatched_order_type(self, thermal_equipment, parameters):
        """Same pattern (delta=+30, upward), requested as Buy -> direction mismatch -> invalid."""
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=30)
        _set_power_pattern(
            thermal_equipment,
            parameters,
            {test_time: 20.0, test_time.add(minutes=15): 20.0, test_time.add(minutes=30): 20.0},
            default=50.0,
        )
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        result = formulator._apply_minimum_stable_power_duration_constraint(test_time, OrderType.Buy, 99.0)
        assert result == (0.0, False, True)

    def test_extends_toward_next_stable_level_for_matching_order_type(self, thermal_equipment, parameters):
        """previous == current (no ramp guard); delta = next(90) - current(50) = 40 -> Sell valid, undivisible."""
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=30)
        _set_power_pattern(
            thermal_equipment,
            parameters,
            {test_time.add(minutes=15): 90.0, test_time.add(minutes=30): 90.0},
            default=50.0,
        )
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        result = formulator._apply_minimum_stable_power_duration_constraint(test_time, OrderType.Sell, 99.0)
        assert result == (40.0, True, True)

    def test_invalid_when_extending_toward_a_zero_previous_level(self, thermal_equipment, parameters):
        """previous=0 -> nothing to extend toward -> invalid, even with next==current avoiding the ramp guard."""
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=15)
        _set_power_pattern(
            thermal_equipment,
            parameters,
            {test_time: 40.0, test_time.add(minutes=15): 40.0, test_time.add(minutes=30): 40.0},
            default=0.0,
        )
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        result = formulator._apply_minimum_stable_power_duration_constraint(test_time, OrderType.Sell, 99.0)
        assert result == (0.0, False, False)


class TestIntegrationWithCase1:
    def test_case_1_order_always_invalidated_once_duration_exceeds_timestep(self, thermal_equipment, parameters):
        """A genuine Case 1 pattern (off at 'time', on at different stable levels
        before/after) hits the ramp guard through _formulate_case_1_order too.
        """
        object.__setattr__(thermal_equipment, "minimum_stable_power_duration", pendulum.duration(minutes=30))
        test_time = parameters.temporal.start_date.add(minutes=30)
        _set_power_pattern(
            thermal_equipment,
            parameters,
            {test_time: 0.0, test_time.add(minutes=15): 60.0, test_time.add(minutes=30): 60.0},
            default=40.0,
        )
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        next_time = test_time.add(minutes=15)

        assert formulator._formulate_case_1_order(test_time, next_time) is None
