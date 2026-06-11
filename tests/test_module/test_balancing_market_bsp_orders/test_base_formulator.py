"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.enums import MarketType, OrderType
from tests.test_module.test_balancing_market_bsp_orders.conftest import make_forecasting_matrix, make_timeseries
from atlas.modules.balancing_market_bsp_orders.order_formulators.base import AbstractOrderFormulator
from atlas.objects.market.order import Order


class ConcreteFormulator(AbstractOrderFormulator):
    def formulate(self):
        return [], []


def _make_formulator(equipment, time_index, parameters) -> ConcreteFormulator:
    return ConcreteFormulator(equipment, time_index, parameters)


class TestComputeProcuredPower:
    def test_rr_activation_includes_mfrr(self, mock_equipment, time_index, parameters):
        """When product_type is rr_activation, mFRR procured power is included."""
        object.__setattr__(mock_equipment, "mfrr_up_procured", make_forecasting_matrix(parameters, 10.0))
        object.__setattr__(mock_equipment, "mfrr_down_procured", make_forecasting_matrix(parameters, 5.0))

        formulator = _make_formulator(mock_equipment, time_index, parameters)
        upward, downward = formulator.compute_procured_power(
            parameters.temporal.execution_date,
            parameters.temporal.start_date,
            parameters.temporal.end_date,
            MarketType.rr_activation,
        )

        assert upward.get_value(parameters.temporal.start_date) == 10.0
        assert downward.get_value(parameters.temporal.start_date) == 5.0

    def test_rr_activation_doesn_t_includes_rr(self, mock_equipment, time_index, parameters):
        """When product_type is rr_activation, RR procured power is not included."""
        object.__setattr__(mock_equipment, "rr_up_procured", make_forecasting_matrix(parameters, 8.0))
        object.__setattr__(mock_equipment, "rr_down_procured", make_forecasting_matrix(parameters, 4.0))

        formulator = _make_formulator(mock_equipment, time_index, parameters)
        upward, downward = formulator.compute_procured_power(
            parameters.temporal.execution_date,
            parameters.temporal.start_date,
            parameters.temporal.end_date,
            MarketType.rr_activation,
        )

        assert upward.get_value(parameters.temporal.start_date) == 0.0
        assert downward.get_value(parameters.temporal.start_date) == 0.0

    def test_mfrr_activation_includes_rr(self, mock_equipment, time_index, parameters):
        """When product_type is mfrr_activation, RR procured power is included."""
        object.__setattr__(mock_equipment, "rr_up_procured", make_forecasting_matrix(parameters, 8.0))
        object.__setattr__(mock_equipment, "rr_down_procured", make_forecasting_matrix(parameters, 4.0))

        formulator = _make_formulator(mock_equipment, time_index, parameters)
        upward, downward = formulator.compute_procured_power(
            parameters.temporal.execution_date,
            parameters.temporal.start_date,
            parameters.temporal.end_date,
            MarketType.mfrr_activation,
        )

        assert upward.get_value(parameters.temporal.start_date) == 8.0
        assert downward.get_value(parameters.temporal.start_date) == 4.0

    def test_mfrr_activation_doesn_t_includes_mfrr(self, mock_equipment, time_index, parameters):
        """When product_type is mfrr_activation, MFRR procured power is not included."""
        object.__setattr__(mock_equipment, "mfrr_up_procured", make_forecasting_matrix(parameters, 8.0))
        object.__setattr__(mock_equipment, "mfrr_down_procured", make_forecasting_matrix(parameters, 4.0))

        formulator = _make_formulator(mock_equipment, time_index, parameters)
        upward, downward = formulator.compute_procured_power(
            parameters.temporal.execution_date,
            parameters.temporal.start_date,
            parameters.temporal.end_date,
            MarketType.mfrr_activation,
        )

        assert upward.get_value(parameters.temporal.start_date) == 0.0
        assert downward.get_value(parameters.temporal.start_date) == 0.0

    def test_fcr_and_afrr_always_included(self, mock_equipment, time_index, parameters):
        """FCR and aFRR get_forecast are always called regardless of product_type."""
        formulator = _make_formulator(mock_equipment, time_index, parameters)
        upward, downward = formulator.compute_procured_power(
            parameters.temporal.execution_date,
            parameters.temporal.start_date,
            parameters.temporal.end_date,
            MarketType.rr_activation,
        )

        assert upward is not None
        assert downward is not None


class TestIsAfterSetupDelay:
    def test_returns_false_within_setup_delay(self, mock_equipment, time_index, parameters):
        """Returns False when the timestep is before the setup delay has elapsed."""
        object.__setattr__(mock_equipment, "setup_delay", 1.0)
        formulator = _make_formulator(mock_equipment, time_index, parameters)

        # execution_date = 23:30 -> setup_delay = 60min -> earliest valid time = 00:30
        time_within_delay = parameters.temporal.execution_date.add(minutes=30)  # 00:00
        assert formulator.is_after_setup_delay(time_within_delay) is False

    def test_returns_true_after_setup_delay(self, mock_equipment, time_index, parameters):
        """Returns True when the timestep is after the setup delay has elapsed."""
        object.__setattr__(mock_equipment, "setup_delay", 0.0)
        formulator = _make_formulator(mock_equipment, time_index, parameters)

        # execution_date = 23:30 -> setup_delay = 0min -> earliest valid time = 23:30
        time_after_delay = parameters.temporal.execution_date.add(minutes=15)  # 23:45
        assert formulator.is_after_setup_delay(time_after_delay) is True

    def test_returns_true_exactly_at_setup_delay(self, mock_equipment, time_index, parameters):
        """Returns True when the timestep is exactly at the setup delay boundary."""
        object.__setattr__(mock_equipment, "setup_delay", 0.5)
        formulator = _make_formulator(mock_equipment, time_index, parameters)

        # execution_date = 23:30 -> setup_delay = 30min -> earliest valid time = 00:00
        time_at_delay = parameters.temporal.execution_date.add(minutes=30)  # 00:00
        assert formulator.is_after_setup_delay(time_at_delay) is True


class TestBuildOrder:
    def _start_end(self, parameters):
        start = parameters.temporal.start_date
        end = start.add(minutes=15)
        return start, end

    def test_returns_none_when_qmax_rounds_to_zero(self, mock_equipment, time_index, parameters):
        formulator = _make_formulator(mock_equipment, time_index, parameters)
        start, end = self._start_end(parameters)

        result = formulator.build_order(OrderType.Sell, start, end, price=10.0, qmin=0.0, qmax=0.4)
        assert result is None

    def test_returns_order_when_qmax_positive(self, mock_equipment, time_index, parameters):
        formulator = _make_formulator(mock_equipment, time_index, parameters)
        start, end = self._start_end(parameters)

        result = formulator.build_order(OrderType.Sell, start, end, price=10.0, qmin=0.0, qmax=50.0)
        assert isinstance(result, Order)

    def test_price_capped_at_market_price_cap(self, mock_equipment, time_index, parameters):
        formulator = _make_formulator(mock_equipment, time_index, parameters)
        start, end = self._start_end(parameters)

        result = formulator.build_order(OrderType.Sell, start, end, price=99999.0, qmin=0.0, qmax=50.0)
        assert result.price == parameters.market_price_cap

    def test_price_capped_at_negative_market_price_cap(self, mock_equipment, time_index, parameters):
        formulator = _make_formulator(mock_equipment, time_index, parameters)
        start, end = self._start_end(parameters)

        result = formulator.build_order(OrderType.Buy, start, end, price=-99999.0, qmin=0.0, qmax=50.0)
        assert result.price == -parameters.market_price_cap

    def test_order_fields_correctly_set(self, mock_equipment, time_index, parameters):
        formulator = _make_formulator(mock_equipment, time_index, parameters)
        start, end = self._start_end(parameters)

        result = formulator.build_order(OrderType.Sell, start, end, price=10.0, qmin=0.0, qmax=50.0)
        assert result.order_type == OrderType.Sell
        assert result.qmin == 0
        assert result.qmax == 50
        assert result.equipment == mock_equipment
        assert result.portfolio == mock_equipment.portfolio
        assert result.market_area == mock_equipment.portfolio.market_area

    def test_order_name_without_suffix(self, mock_equipment, time_index, parameters):
        formulator = _make_formulator(mock_equipment, time_index, parameters)
        start, end = self._start_end(parameters)

        result = formulator.build_order(OrderType.Sell, start, end, price=10.0, qmin=0.0, qmax=50.0)
        assert "test_equipment" in result.name
        assert "_U_" in result.name
        assert "at_" in result.name
        assert not result.name.endswith("_")

    def test_order_name_with_suffix(self, mock_equipment, time_index, parameters):
        formulator = _make_formulator(mock_equipment, time_index, parameters)
        start, end = self._start_end(parameters)

        result = formulator.build_order(OrderType.Sell, start, end, price=10.0, qmin=0.0, qmax=50.0, suffix="_custom")
        assert result.name.endswith("_custom")
