"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest

from atlas.math.matrix import ScenarioMatrix
from atlas.enums import OrderType
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.modules.balancing_market_bsp_orders.input_objects.hydro import BalancingHydro
from atlas.modules.balancing_market_bsp_orders.order_formulators.hydro import HydraulicOrderFormulator
from atlas.modules.balancing_market_bsp_orders.order_formulators.hydro import extract_mean_from_scenario
from tests.test_module.test_balancing_market_bsp_orders.conftest import make_forecasting_matrix, make_timeseries

def make_scenario_matrix(parameters, value: float) -> ScenarioMatrix:
    """
    Build a ScenarioMatrix with a single scenario covering the full time frame.

    :param parameters: Module parameters providing temporal context
    :type parameters: BSPBalancingOrdersParameters
    :param value: Constant value for all scenario entries
    :type value: float
    :return: A ScenarioMatrix with one scenario column
    :rtype: ScenarioMatrix
    """
    ts = make_timeseries(parameters, value)
    sm = ScenarioMatrix()
    sm.add(ts, "0")
    return sm


def make_stored_energy(parameters, value: float) -> ForecastingMatrix:
    """Build a ForecastingMatrix for stored_energy with a constant value."""
    return make_forecasting_matrix(parameters, value)


def _make_hydro_equipment(parameters, real_market_objects, **kwargs):
    """Build a BalancingHydro with model_construct, accepting field overrides"""
    defaults = dict(
        name="test_hydro",
        node=real_market_objects["node"],
        portfolio=real_market_objects["portfolio"],
        setup_delay=0.0,
        maximum_gradient=0.0,
        has_daily_energy_constraint=False,
        maximum_daily_energy=None,
        minimum_daily_energy=None,
        power=make_forecasting_matrix(parameters, 50.0),
        maximum_power=make_timeseries(parameters, 100.0),
        minimum_power=make_timeseries(parameters, 0.0),
        stored_energy=make_stored_energy(parameters, 500.0),
        storage_marginal_value=make_scenario_matrix(parameters, 10.0),
        fragment_prices=[5.0, 10.0],
        fragment_volumes=[0.5, 0.5],
    )
    defaults.update(kwargs)
    return BalancingHydro.model_construct(**defaults)


def _make_formulator(equipment, time_index, parameters) -> HydraulicOrderFormulator:
    return HydraulicOrderFormulator(equipment, time_index, parameters)


class TestHydraulicOrderFormulatorOrders:
    def test_no_orders_when_setup_delay_not_elapsed(self, time_index, parameters, real_market_objects):
        """No orders are formulated when setup_delay exceeds the entire time frame"""
        equipment = _make_hydro_equipment(parameters, real_market_objects, setup_delay=24.0)

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        assert orders == []

    def test_upward_orders_formulated_when_available(self, time_index, parameters, real_market_objects):
        """Sell orders are formulated when upward power is available.

        max_power = 100, forecasted_power = 50 -> upward_available = 50 >= 1
        """
        equipment = _make_hydro_equipment(
            parameters, real_market_objects,
            power=make_forecasting_matrix(parameters, 50.0),
            maximum_power=make_timeseries(parameters, 100.0),
            minimum_power=make_timeseries(parameters, 0.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell]
        assert len(upward_orders) > 0

    def test_no_upward_orders_when_not_available(self, time_index, parameters, real_market_objects):
        """No Sell orders when forecasted_power == max_power.

        upward_available = 100 - 100 = 0 < 1
        """
        equipment = _make_hydro_equipment(
            parameters, real_market_objects,
            power=make_forecasting_matrix(parameters, 100.0),
            maximum_power=make_timeseries(parameters, 100.0),
            minimum_power=make_timeseries(parameters, 0.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell]
        assert upward_orders == []

    def test_downward_orders_formulated_when_available(self, time_index, parameters, real_market_objects):
        """Buy orders are formulated when downward power is available.

        forecasted_power = 50, min_power = 0 -> downward_available = 50 >= 1
        """
        equipment = _make_hydro_equipment(
            parameters, real_market_objects,
            power=make_forecasting_matrix(parameters, 50.0),
            maximum_power=make_timeseries(parameters, 100.0),
            minimum_power=make_timeseries(parameters, 0.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        downward_orders = [o for o in orders if o.order_type == OrderType.Buy]
        assert len(downward_orders) > 0

    def test_no_downward_orders_when_not_available(self, time_index, parameters, real_market_objects):
        """No Buy orders when forecasted_power == min_power.

        downward_available = 50 - 50 = 0 < 1
        """
        equipment = _make_hydro_equipment(
            parameters, real_market_objects,
            power=make_forecasting_matrix(parameters, 50.0),
            maximum_power=make_timeseries(parameters, 100.0),
            minimum_power=make_timeseries(parameters, 50.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        downward_orders = [o for o in orders if o.order_type == OrderType.Buy]
        assert downward_orders == []

    def test_fragment_suffix_in_order_names(self, time_index, parameters, real_market_objects):
        """Orders have fragment suffixes in their names."""
        equipment = _make_hydro_equipment(
            parameters, real_market_objects,
            power=make_forecasting_matrix(parameters, 50.0),
            maximum_power=make_timeseries(parameters, 100.0),
            minimum_power=make_timeseries(parameters, 0.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        assert all("_frag_" in o.name for o in orders)

    def test_no_order_couplings_returned(self, time_index, parameters, real_market_objects):
        """Hydraulic formulator never returns order couplings."""
        equipment = _make_hydro_equipment(parameters, real_market_objects)

        _, couplings = _make_formulator(equipment, time_index, parameters).formulate()
        assert couplings == []

    def test_order_price_includes_water_value(self, time_index, parameters, real_market_objects):
        """Order price = water_value + fragment_price.

        scenario_matrix value = 10.0, fragment_prices = [5.0, 10.0]
        -> first fragment price >= 15.0
        """
        equipment = _make_hydro_equipment(
            parameters, real_market_objects,
            power=make_forecasting_matrix(parameters, 50.0),
            maximum_power=make_timeseries(parameters, 100.0),
            minimum_power=make_timeseries(parameters, 0.0),
            storage_marginal_value=make_scenario_matrix(parameters, 10.0),
            fragment_prices=[5.0, 10.0],
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell]
        assert all(o.price >= 15.0 for o in upward_orders)


class TestExtractMeanFromScenario:
    def test_returns_zero_when_matrix_empty(self, parameters, real_market_objects):
        """Returns 0.0 when the scenario matrix has no indexes."""
        sm = ScenarioMatrix()
        result = extract_mean_from_scenario(sm, 500.0, parameters.temporal.start_date)
        assert result == 0.0

    def test_clamps_to_lower_bound(self, parameters, real_market_objects):
        """Clamps to the first scenario value when index_input is below range."""
        sm = make_scenario_matrix(parameters, 20.0)
        result = extract_mean_from_scenario(sm, -999.0, parameters.temporal.start_date)
        assert result == pytest.approx(20.0)

    def test_clamps_to_upper_bound(self, parameters, real_market_objects):
        """Clamps to the last scenario value when index_input is above range."""
        sm = make_scenario_matrix(parameters, 20.0)
        result = extract_mean_from_scenario(sm, 999999.0, parameters.temporal.start_date)
        assert result == pytest.approx(20.0)

    def test_interpolates_between_scenarios(self, parameters, real_market_objects):
        """Linearly interpolates between two surrounding scenario values.

        scenario "0" = 10.0, scenario "1000" = 20.0
        index_input = 500 -> result = 15.0
        """
        ts_low = make_timeseries(parameters, 10.0)
        ts_high = make_timeseries(parameters, 20.0)
        sm = ScenarioMatrix()
        sm.add(ts_low, "0")
        sm.add(ts_high, "1000")

        result = extract_mean_from_scenario(sm, 500.0, parameters.temporal.start_date)
        assert result == pytest.approx(15.0)

    def test_exact_match_returns_scenario_value(self, parameters, real_market_objects):
        """Returns exact value when index_input matches a scenario index exactly."""
        ts_low = make_timeseries(parameters, 10.0)
        ts_high = make_timeseries(parameters, 20.0)
        sm = ScenarioMatrix()
        sm.add(ts_low, "0")
        sm.add(ts_high, "1000")

        result = extract_mean_from_scenario(sm, 1000.0, parameters.temporal.start_date)
        assert result == pytest.approx(20.0)
