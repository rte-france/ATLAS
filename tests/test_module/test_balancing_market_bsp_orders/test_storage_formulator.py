"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.enums import OrderType, StorageType
from atlas.modules.balancing_market_bsp_orders.input_objects.storage import BalancingStorage
from atlas.modules.balancing_market_bsp_orders.order_formulators.storage import StorageOrderFormulator
from tests.test_module.test_balancing_market_bsp_orders.conftest import make_forecasting_matrix, make_timeseries


@pytest.fixture(scope="function")
def market_objects_with_prices(real_market_objects, parameters):
    """Extend real_market_objects with da_price required by compute_average_clearing_prices."""
    from atlas.math.timeseries import Timeseries
    da_price = Timeseries.from_index(
        start_date=parameters.temporal.start_date,
        frequency=parameters.temporal.timestep,
        end_date=parameters.temporal.end_date,
        default_value=50.0,
    )
    object.__setattr__(real_market_objects["market_area"], "da_price", da_price)
    return real_market_objects


def _make_storage_equipment(parameters, real_market_objects, **kwargs):
    """Build a BalancingStorage with model_construct, accepting field overrides."""
    defaults = dict(
        name="test_storage",
        node=real_market_objects["node"],
        portfolio=real_market_objects["portfolio"],
        setup_delay=0.0,
        maximum_gradient=0.0,
        storage_type=StorageType.BATTERY,
        transition_duration=pendulum.duration(hours=0),
        charge_efficiency=1.0,
        power=make_forecasting_matrix(parameters, 50.0),
        maximum_power=make_timeseries(parameters, 100.0),
        minimum_power=make_timeseries(parameters, 0.0),
        maximum_energy=make_timeseries(parameters, 1000.0),
        minimum_state_of_charge=make_timeseries(parameters, 0.0),
        discharge_efficiency=1.0,
        stored_energy=make_forecasting_matrix(parameters, 500.0),
        variable_cost=make_timeseries(parameters, 10.0),
        # Activated power fields needed by compute_daily_balancing_energy
        rr_activated=make_timeseries(parameters, 0.0),
        mfrr_activated=make_timeseries(parameters, 0.0),
        afrr_activated=make_timeseries(parameters, 0.0),
        fcr_activated=make_timeseries(parameters, 0.0),
        specific_activated_power=make_forecasting_matrix(parameters, 0.0),
    )
    defaults.update(kwargs)
    return BalancingStorage.model_construct(**defaults)


def _make_formulator(equipment, time_index, parameters) -> StorageOrderFormulator:
    return StorageOrderFormulator(equipment, time_index, parameters)


class TestStorageOrderFormulatorOrders:
    def test_no_orders_when_setup_delay_not_elapsed(self, time_index, parameters, market_objects_with_prices):
        """No orders are formulated when setup_delay exceeds the entire time frame."""
        equipment = _make_storage_equipment(parameters, market_objects_with_prices, setup_delay=24.0)

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        assert orders == []

    def test_upward_order_formulated_when_available(self, time_index, parameters, market_objects_with_prices):
        """A Sell order is formulated when upward power is available and storage allows it.

        max_power = 100, forecasted_power = 50 -> upward_available = 50
        stored_energy = 500 > min_energy = 0 -> storage constraint ok
        """
        equipment = _make_storage_equipment(
            parameters, market_objects_with_prices,
            power=make_forecasting_matrix(parameters, 50.0),
            maximum_power=make_timeseries(parameters, 100.0),
            minimum_power=make_timeseries(parameters, 0.0),
            stored_energy=make_forecasting_matrix(parameters, 500.0),
            maximum_energy=make_timeseries(parameters, 1000.0),
            minimum_state_of_charge=make_timeseries(parameters, 0.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell]
        assert len(upward_orders) == len(time_index)

    def test_no_upward_order_when_stored_energy_at_minimum(self, time_index, parameters, market_objects_with_prices):
        """No Sell order when stored_energy <= minimum_state_of_charge * maximum_energy.

        stored_energy = 100, min_soc = 0.1, max_energy = 1000 -> min_energy = 100 -> invalid
        """
        equipment = _make_storage_equipment(
            parameters, market_objects_with_prices,
            power=make_forecasting_matrix(parameters, 50.0),
            maximum_power=make_timeseries(parameters, 100.0),
            stored_energy=make_forecasting_matrix(parameters, 100.0),
            maximum_energy=make_timeseries(parameters, 1000.0),
            minimum_state_of_charge=make_timeseries(parameters, 0.1),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell]
        assert upward_orders == []

    def test_downward_order_formulated_when_available(self, time_index, parameters, market_objects_with_prices):
        """A Buy order is formulated when downward power is available and storage allows it.

        forecasted_power = 50, min_power = 0 -> downward_available = 50
        max_energy = 1000 > stored_energy = 500 -> storage constraint ok
        """
        equipment = _make_storage_equipment(
            parameters, market_objects_with_prices,
            power=make_forecasting_matrix(parameters, 50.0),
            minimum_power=make_timeseries(parameters, 0.0),
            stored_energy=make_forecasting_matrix(parameters, 500.0),
            maximum_energy=make_timeseries(parameters, 1000.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        downward_orders = [o for o in orders if o.order_type == OrderType.Buy]
        assert len(downward_orders) == len(time_index)

    def test_no_downward_order_when_storage_full(self, time_index, parameters, market_objects_with_prices):
        """No Buy order when stored_energy >= maximum_energy.

        stored_energy = 1000 = max_energy -> no room to charge -> invalid
        """
        equipment = _make_storage_equipment(
            parameters, market_objects_with_prices,
            power=make_forecasting_matrix(parameters, 50.0),
            minimum_power=make_timeseries(parameters, 0.0),
            stored_energy=make_forecasting_matrix(parameters, 1000.0),
            maximum_energy=make_timeseries(parameters, 1000.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        downward_orders = [o for o in orders if o.order_type == OrderType.Buy]
        assert downward_orders == []

    def test_no_order_couplings_returned(self, time_index, parameters, market_objects_with_prices):
        """Storage formulator never returns order couplings."""
        equipment = _make_storage_equipment(parameters, market_objects_with_prices)

        _, couplings = _make_formulator(equipment, time_index, parameters).formulate()
        assert couplings == []


class TestStoragePHSTransitionConstraint:
    def test_no_phs_constraint_for_battery(self, time_index, parameters, market_objects_with_prices):
        """PHS transition constraint is not applied for BATTERY storage type."""
        equipment = _make_storage_equipment(
            parameters, market_objects_with_prices,
            storage_type=StorageType.BATTERY,
            transition_duration=pendulum.duration(hours=1),
            power=make_forecasting_matrix(parameters, 0.0),
            maximum_power=make_timeseries(parameters, 100.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        # Battery with zero forecasted power: downward only (PHS would block upward)
        # For battery, constraint doesn't apply -> both directions possible if power available
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell]
        assert len(upward_orders) == len(time_index)

    def test_phs_upward_blocked_when_forecast_is_zero(self, time_index, parameters, market_objects_with_prices):
        """PHS: no Sell order when forecasted_power == 0 and transition_duration >= 1 timestep."""
        equipment = _make_storage_equipment(
            parameters, market_objects_with_prices,
            storage_type=StorageType.PUMPED_HYDRAULIC_STORAGE,
            transition_duration=pendulum.duration(hours=1),
            power=make_forecasting_matrix(parameters, 0.0),
            maximum_power=make_timeseries(parameters, 100.0),
            minimum_power=make_timeseries(parameters, -100.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell]
        assert upward_orders == []

    def test_phs_downward_blocked_when_forecast_is_zero(self, time_index, parameters, market_objects_with_prices):
        """PHS: no Buy order when forecasted_power == 0 and transition_duration >= 1 timestep."""
        equipment = _make_storage_equipment(
            parameters, market_objects_with_prices,
            storage_type=StorageType.PUMPED_HYDRAULIC_STORAGE,
            transition_duration=pendulum.duration(hours=1),
            power=make_forecasting_matrix(parameters, 0.0),
            maximum_power=make_timeseries(parameters, 100.0),
            minimum_power=make_timeseries(parameters, -100.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        downward_orders = [o for o in orders if o.order_type == OrderType.Buy]
        assert downward_orders == []

    def test_phs_upward_limited_when_forecast_negative(self, time_index, parameters, market_objects_with_prices):
        """PHS: upward qmax capped at abs(forecasted_power) when forecast is negative (pumping).

        forecasted_power = -30, max_power = 100 -> upward limited to 30
        """
        equipment = _make_storage_equipment(
            parameters, market_objects_with_prices,
            storage_type=StorageType.PUMPED_HYDRAULIC_STORAGE,
            transition_duration=pendulum.duration(hours=1),
            power=make_forecasting_matrix(parameters, -30.0),
            maximum_power=make_timeseries(parameters, 100.0),
            minimum_power=make_timeseries(parameters, -100.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell]
        assert all(o.qmax <= 30 for o in upward_orders)

    def test_phs_no_constraint_when_transition_duration_zero(self, time_index, parameters, market_objects_with_prices):
        """PHS: no transition constraint when transition_duration < 1 timestep."""
        equipment = _make_storage_equipment(
            parameters, market_objects_with_prices,
            storage_type=StorageType.PUMPED_HYDRAULIC_STORAGE,
            transition_duration=pendulum.duration(seconds=0),
            power=make_forecasting_matrix(parameters, 0.0),
            maximum_power=make_timeseries(parameters, 100.0),
            minimum_power=make_timeseries(parameters, -100.0),
        )

        orders, _ = _make_formulator(equipment, time_index, parameters).formulate()
        # With zero transition duration, PHS constraint doesn't apply
        # upward_available = 100 - 0 = 100 -> orders should be formulated
        upward_orders = [o for o in orders if o.order_type == OrderType.Sell]
        assert len(upward_orders) == len(time_index)
