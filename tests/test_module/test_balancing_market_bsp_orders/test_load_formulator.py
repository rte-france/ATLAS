"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest

from atlas.enums import OrderType
from atlas.modules.balancing_market_bsp_orders.order_formulators.load import LoadOrderFormulator
from tests.test_module.test_balancing_market_bsp_orders.conftest import make_forecasting_matrix


def _make_formulator(equipment, time_index, parameters) -> LoadOrderFormulator:
    return LoadOrderFormulator(equipment, time_index, parameters)


class TestLoadOrderFormulatorOrders:
    def test_no_orders_when_setup_delay_not_elapsed(self, mock_equipment, time_index, parameters):
        object.__setattr__(mock_equipment, 'setup_delay', 24.0)

        orders, _ = _make_formulator(mock_equipment, time_index, parameters).formulate()
        assert orders == []

    def test_upward_order_formulated_when_available(self, mock_equipment, time_index, parameters):
        """A Sell order is formulated when upward power is available.

        upward_available = -forecasted_power - upward_procured
        With power = -60 (negative load) and procured = 0: upward = 60 > 0 -> Sell order.
        """
        object.__setattr__(mock_equipment, 'power', make_forecasting_matrix(parameters, -60.0))

        orders, _ = _make_formulator(mock_equipment, time_index, parameters).formulate()
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell]
        assert len(upward_orders) == len(time_index)

    def test_no_upward_order_when_not_available(self, mock_equipment, time_index, parameters):
        """No Sell order is formulated when upward power is zero or negative.

        upward_available = -forecasted_power - upward_procured
        With power = 50 and procured = 0: upward = -50 <= 0 -> no Sell order.
        """
        object.__setattr__(mock_equipment, 'power', make_forecasting_matrix(parameters, 50.0))

        orders, _ = _make_formulator(mock_equipment, time_index, parameters).formulate()
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell]
        assert upward_orders == []

    def test_downward_order_formulated_when_available(self, mock_equipment, time_index, parameters):
        """A Buy order is formulated when downward power is >= 1 MW.

        downward_available = forecasted_power - max_power - downward_procured
        With power = 100, max_power = 50, procured = 0: downward = 50 >= 1 -> Buy order.
        """
        object.__setattr__(mock_equipment, 'power', make_forecasting_matrix(parameters, 100.0))
        object.__setattr__(mock_equipment, 'maximum_power_forecast', make_forecasting_matrix(parameters, 50.0))

        orders, _ = _make_formulator(mock_equipment, time_index, parameters).formulate()
        downward_orders = [o for o in orders if o.order_type == OrderType.Buy]
        assert len(downward_orders) == len(time_index)

    def test_no_downward_order_when_below_threshold(self, mock_equipment, time_index, parameters):
        """No Buy order is formulated when downward power is below 1 MW.

        downward_available = forecasted_power - max_power - downward_procured
        With power = 50, max_power = 50, procured = 0: downward = 0 < 1 -> no Buy order.
        """
        object.__setattr__(mock_equipment, 'power', make_forecasting_matrix(parameters, 50.0))
        object.__setattr__(mock_equipment, 'maximum_power_forecast', make_forecasting_matrix(parameters, 50.0))

        orders, _ = _make_formulator(mock_equipment, time_index, parameters).formulate()
        downward_orders = [o for o in orders if o.order_type == OrderType.Buy]
        assert downward_orders == []

    def test_both_orders_formulated_when_both_available(self, mock_equipment, time_index, parameters):
        """Both Sell and Buy orders are formulated when both directions are available.

        upward_available = -forecasted_power = -(-60) = 60 > 0 -> Sell order.
        downward_available = forecasted_power - max_power = -60 - (-110) = 50 >= 1 -> Buy order.
        """
        object.__setattr__(mock_equipment, 'power', make_forecasting_matrix(parameters, -60.0))
        object.__setattr__(mock_equipment, 'maximum_power_forecast', make_forecasting_matrix(parameters, -110.0))

        orders, _ = _make_formulator(mock_equipment, time_index, parameters).formulate()
        assert len([o for o in orders if o.order_type == OrderType.Sell]) == len(time_index)
        assert len([o for o in orders if o.order_type == OrderType.Buy]) == len(time_index)

    def test_no_order_couplings_returned(self, mock_equipment, time_index, parameters):
        _, couplings = _make_formulator(mock_equipment, time_index, parameters).formulate()
        assert couplings == []
