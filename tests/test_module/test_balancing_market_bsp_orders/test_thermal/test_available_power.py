"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from atlas import ForecastingMatrix, Timeseries
from atlas.enums import OrderType
from atlas.modules.balancing_market_bsp_orders.order_formulators.thermal import ThermalOrderFormulator
from tests.test_module.test_balancing_market_bsp_orders.conftest import make_forecasting_matrix


def _make_formulator(equipment, time_index, parameters) -> ThermalOrderFormulator:
    return ThermalOrderFormulator(equipment, time_index, parameters)


def _upward_orders(orders):
    """Regular upward (Sell) orders, identified by the '_u_' direction segment."""
    return [o for o in orders if o.order_type == OrderType.Sell and "_u_" in o.name]


def _downward_orders(orders):
    """Regular downward (Buy) orders, identified by the '_d_' direction segment —
    excludes shutdown orders ('_s_'), which may coexist and are covered separately
    in test_shutdown.py.
    """
    return [o for o in orders if o.order_type == OrderType.Buy and "_d_" in o.name]


class TestUpwardAvailablePower:
    def test_upward_order_formulated_with_available_power(self, thermal_equipment, time_index, parameters):
        """upward_available = maximum_power - forecasted_power = 100 - 50 = 50."""
        orders, _ = _make_formulator(thermal_equipment, time_index, parameters).formulate()
        upward_orders = _upward_orders(orders)
        assert len(upward_orders) == len(time_index)
        assert all(o.qmax == 50 for o in upward_orders)
        assert all(o.qmin == 0 for o in upward_orders)
        assert all(o.price == 80 for o in upward_orders)

    def test_no_upward_order_when_power_at_maximum(self, thermal_equipment, time_index, parameters):
        """upward_available = 100 - 100 = 0 -> no Sell order."""
        object.__setattr__(thermal_equipment, "power", make_forecasting_matrix(parameters, 100.0))

        orders, _ = _make_formulator(thermal_equipment, time_index, parameters).formulate()
        assert _upward_orders(orders) == []

    def test_no_upward_order_below_one_mw_threshold(self, thermal_equipment, time_index, parameters):
        """upward_available = 100 - 99.4 = 0.6 < 1 MW -> no Sell order, even though > 0."""
        object.__setattr__(thermal_equipment, "power", make_forecasting_matrix(parameters, 99.4))

        orders, _ = _make_formulator(thermal_equipment, time_index, parameters).formulate()
        assert _upward_orders(orders) == []


class TestDownwardAvailablePower:
    def test_downward_order_formulated_with_available_power(self, thermal_equipment, time_index, parameters):
        """downward_available = forecasted_power - minimum_power = 50 - 20 = 30."""
        orders, _ = _make_formulator(thermal_equipment, time_index, parameters).formulate()
        downward_orders = _downward_orders(orders)
        assert len(downward_orders) == len(time_index)
        assert all(o.qmax == 30 for o in downward_orders)
        assert all(o.qmin == 0 for o in downward_orders)
        assert all(o.price == 80 for o in downward_orders)

    def test_no_downward_order_below_one_mw_threshold(self, thermal_equipment, time_index, parameters):
        """downward_available = 20.6 - 20 = 0.6 < 1 MW -> no regular Buy order."""
        object.__setattr__(thermal_equipment, "power", make_forecasting_matrix(parameters, 20.6))

        orders, _ = _make_formulator(thermal_equipment, time_index, parameters).formulate()
        assert _downward_orders(orders) == []


class TestStartupRampGuard:
    def test_ramp_guard_zeroes_both_directions(self, thermal_equipment, time_index, parameters):
        """0 < power(10) < minimum_power(20) -> both upward and downward available
        power are forced to 0, regardless of maximum_power/minimum_power headroom.
        """
        object.__setattr__(thermal_equipment, "power", make_forecasting_matrix(parameters, 10.0))

        orders, _ = _make_formulator(thermal_equipment, time_index, parameters).formulate()
        assert _upward_orders(orders) == []
        assert _downward_orders(orders) == []


class TestProcuredPower:
    def test_upward_procured_power_reduces_available_power(self, thermal_equipment, time_index, parameters):
        """upward_available = 100 - 50 - 10(FCR up procured) = 40."""
        object.__setattr__(thermal_equipment, "fcr_up_procured", make_forecasting_matrix(parameters, 10.0))

        orders, _ = _make_formulator(thermal_equipment, time_index, parameters).formulate()
        upward_orders = _upward_orders(orders)
        assert len(upward_orders) == len(time_index)
        assert all(o.qmax == 40 for o in upward_orders)

    def test_downward_procured_power_reduces_available_power(self, thermal_equipment, time_index, parameters):
        """downward_available = 50 - 20 - 10(FCR down procured) = 20."""
        object.__setattr__(thermal_equipment, "fcr_down_procured", make_forecasting_matrix(parameters, 10.0))

        orders, _ = _make_formulator(thermal_equipment, time_index, parameters).formulate()
        downward_orders = _downward_orders(orders)
        assert len(downward_orders) == len(time_index)
        assert all(o.qmax == 20 for o in downward_orders)


class TestSetupDelay:
    def test_no_orders_when_setup_delay_not_elapsed(self, thermal_equipment, time_index, parameters):
        """setup_delay (24h) exceeds the entire balancing time frame -> no orders at all."""
        object.__setattr__(thermal_equipment, "setup_delay", 24.0)

        orders, _ = _make_formulator(thermal_equipment, time_index, parameters).formulate()
        assert orders == []


class TestGradientConstraint:
    def _make_forecasted_power(self, parameters, overrides):
        """Full-range forecast covering parameters.temporal's whole window (a
        constant 50.0 baseline), with specific timesteps overridden. formulate()
        computes forecasted_power/min_power/max_power over the full [start_date,
        end_date] window regardless of target_times, so the underlying power
        matrix has to cover that whole range too, not just the timesteps we
        actually target.
        """
        ts = Timeseries.from_index(
            start_date=parameters.temporal.start_date,
            frequency=parameters.temporal.timestep,
            end_date=parameters.temporal.end_date,
            default_value=50.0,
        )
        for dt, value in overrides.items():
            ts.set_value(dt, value)

        fm = ForecastingMatrix()
        fm.add(ts, parameters.temporal.execution_date)
        return fm

    def test_gradient_narrows_upward_and_can_clamp_downward_to_zero(self, thermal_equipment, parameters):
        """maximum_gradient = 2 MW/min -> max_grad = 2 * 15 = 30 MW per timestep.
        previous=50, current=50 (both from the 50.0 baseline), next=90 (a sharp
        upward evolution just after 'time').

        upward_available before gradient = 100 - 50 = 50
          -> min(50, 30 - prev_upward_evo(0), 30 - next_downward_evo(0)) = 30
        downward_available before gradient = 50 - 20 = 30
          -> min(30, 30 - prev_downward_evo(0), 30 - next_upward_evo(40)) = -10 -> clamped to 0

        target_times is restricted to 'time' itself so only that timestep is
        formulated, even though the underlying power forecast spans the full
        balancing window.
        """
        object.__setattr__(thermal_equipment, "maximum_gradient", 2.0)

        test_time = parameters.temporal.start_date.add(minutes=15)
        next_time = test_time.add(minutes=15)
        object.__setattr__(
            thermal_equipment, "power", self._make_forecasted_power(parameters, {next_time: 90.0})
        )

        orders, _ = _make_formulator(thermal_equipment, [test_time], parameters).formulate()

        upward_orders = _upward_orders(orders)
        assert len(upward_orders) == 1
        assert upward_orders[0].qmax == 30

        assert _downward_orders(orders) == []
