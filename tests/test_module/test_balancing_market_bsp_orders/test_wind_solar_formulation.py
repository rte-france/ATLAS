"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest

from atlas.enums import OrderType
from atlas.objects.equipment.wind import Wind
from atlas.modules.balancing_market_bsp_orders.order_formulators.wind_solar import WindPvOrderFormulator
from tests.test_module.test_balancing_market_bsp_orders.conftest import make_forecasting_matrix, make_timeseries


@pytest.fixture(scope="function")
def wind_equipment(parameters, real_market_objects):
    return Wind.model_construct(
        name="test_wind",
        node=real_market_objects["node"],
        portfolio=real_market_objects["portfolio"],
        setup_delay=0.0,
        maximum_gradient=0.0,
        power=make_forecasting_matrix(parameters, 100.0),
        maximum_power_forecast=make_forecasting_matrix(parameters, 100.0),
        maximum_curtailment_ratio=make_timeseries(parameters, 0.0),
        fcr_up_procured=make_forecasting_matrix(parameters, 0.0),
        fcr_down_procured=make_forecasting_matrix(parameters, 0.0),
        afrr_up_procured=make_forecasting_matrix(parameters, 0.0),
        afrr_down_procured=make_forecasting_matrix(parameters, 0.0),
        mfrr_up_procured=make_forecasting_matrix(parameters, 0.0),
        mfrr_down_procured=make_forecasting_matrix(parameters, 0.0),
        rr_up_procured=make_forecasting_matrix(parameters, 0.0),
        rr_down_procured=make_forecasting_matrix(parameters, 0.0),
        variable_cost=make_timeseries(parameters, 10.0),
    )


def _make_formulator(equipment, time_index, parameters) -> WindPvOrderFormulator:
    return WindPvOrderFormulator(equipment, time_index, parameters)


class TestWindSolarOrderFormulatorOrders:
    def test_no_orders_when_setup_delay_not_elapsed(self, wind_equipment, time_index, parameters_self_balancing):
        """No orders are formulated when setup_delay exceeds the entire time frame."""
        object.__setattr__(wind_equipment, 'setup_delay', 24.0)

        orders, _ = _make_formulator(wind_equipment, time_index, parameters_self_balancing).formulate()
        assert orders == []

    def test_no_upward_order_when_res_self_balancing_is_false(self, wind_equipment, time_index, parameters):
        """No Sell order is formulated when res_self_balancing is False, even when upward power is available.

        upward_available = max_power - forecasted_power = 100 - 50 = 50 > 0, but res_self_balancing = False.
        """
        object.__setattr__(wind_equipment, 'power', make_forecasting_matrix(parameters, 50.0))

        orders, _ = _make_formulator(wind_equipment, time_index, parameters).formulate()
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell]
        assert upward_orders == []

    def test_upward_order_formulated_when_res_self_balancing_is_true(
        self, wind_equipment, time_index, parameters_self_balancing
    ):
        """A Sell order is formulated when res_self_balancing is True and upward power is available.

        upward_available = max_power - forecasted_power = 100 - 50 = 50 > 0.
        """
        object.__setattr__(wind_equipment, 'power', make_forecasting_matrix(parameters_self_balancing, 50.0))
        object.__setattr__(wind_equipment, 'maximum_power_forecast', make_forecasting_matrix(parameters_self_balancing, 100.0))
        object.__setattr__(wind_equipment, 'maximum_curtailment_ratio', make_timeseries(parameters_self_balancing, 0.0))

        orders, _ = _make_formulator(wind_equipment, time_index, parameters_self_balancing).formulate()
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell and "_selfbal" in o.name]
        assert len(upward_orders) == len(time_index)

    def test_regular_downward_order_formulated_when_available(self, wind_equipment, time_index, parameters):
        """A regular Buy order is formulated when downward power >= 1 MW.

        downward_available = forecasted_power - min_power = 100 - 50 = 50 >= 1.
        (curtailment_ratio = 0.5 -> min_power = max_power * 0.5 = 50)
        """
        object.__setattr__(wind_equipment, 'maximum_curtailment_ratio', make_timeseries(parameters, 0.5))

        orders, _ = _make_formulator(wind_equipment, time_index, parameters).formulate()
        regular_orders = [o for o in orders if o.order_type == OrderType.Buy and "_selfbal" not in o.name]
        assert len(regular_orders) == len(time_index)

    def test_no_downward_order_when_below_threshold(self, wind_equipment, time_index, parameters):
        """No Buy order when downward power < 1 MW.

        forecasted_power = max_power and curtailment_ratio = 0 -> downward_available = 0.
        """
        object.__setattr__(wind_equipment, 'power', make_forecasting_matrix(parameters, 100.0))
        object.__setattr__(wind_equipment, 'maximum_curtailment_ratio', make_timeseries(parameters, 0.0))

        orders, _ = _make_formulator(wind_equipment, time_index, parameters).formulate()
        downward_orders = [o for o in orders if o.order_type == OrderType.Buy]
        assert downward_orders == []

    def test_self_balancing_downward_order_when_forecast_exceeds_max(
        self, wind_equipment, time_index, parameters_self_balancing
    ):
        """A self-balancing Buy order is formulated when forecasted_power > max_power and res_self_balancing is True.

        self_bal_qmax = forecasted_power - max_power = 120 - 100 = 20 >= 1.
        """
        object.__setattr__(wind_equipment, 'power', make_forecasting_matrix(parameters_self_balancing, 120.0))
        object.__setattr__(wind_equipment, 'maximum_power_forecast', make_forecasting_matrix(parameters_self_balancing, 100.0))
        object.__setattr__(wind_equipment, 'maximum_curtailment_ratio', make_timeseries(parameters_self_balancing, 0.0))

        orders, _ = _make_formulator(wind_equipment, time_index, parameters_self_balancing).formulate()
        self_bal_orders = [o for o in orders if o.order_type == OrderType.Buy and "_selfbal" in o.name]
        assert len(self_bal_orders) == len(time_index)

    def test_self_balancing_order_priced_at_market_price_cap(
        self, wind_equipment, time_index, parameters_self_balancing
    ):
        object.__setattr__(wind_equipment, 'power', make_forecasting_matrix(parameters_self_balancing, 120.0))
        object.__setattr__(wind_equipment, 'maximum_power_forecast', make_forecasting_matrix(parameters_self_balancing, 100.0))
        object.__setattr__(wind_equipment, 'maximum_curtailment_ratio', make_timeseries(parameters_self_balancing, 0.0))

        orders, _ = _make_formulator(wind_equipment, time_index, parameters_self_balancing).formulate()
        self_bal_orders = [o for o in orders if o.order_type == OrderType.Buy and "_selfbal" in o.name]
        assert all(o.price == parameters_self_balancing.market_price_cap for o in self_bal_orders)

    def test_no_order_couplings_returned(self, wind_equipment, time_index, parameters):
        _, couplings = _make_formulator(wind_equipment, time_index, parameters).formulate()
        assert couplings == []
