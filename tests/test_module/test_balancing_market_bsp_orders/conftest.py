"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from unittest.mock import MagicMock

import pytest

from atlas.timing import generate_datetimes
from atlas.enums import MarketType
from atlas.modules.balancing_market_bsp_orders.parameters import BSPBalancingOrdersParameters
from atlas.objects.equipment.load import Load
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock

PARAMETERS_DICT = {
    "temporal": {
        "start_date": "2028-09-02 00:00:00",
        "execution_date": "2028-09-01 23:30:00",
        "end_date": "2028-09-02 01:00:00",
        "timestep": "PT15M",
    },
    "product_type": MarketType.rr_activation,
    "market_price_cap": 15000,
    "with_combinatorial_options": True,
    "market_area_names": "all",
    "conservative_stored_energy": True,
    "storage_price_threshold": 0.1,
    "res_self_balancing": False,
}


@pytest.fixture(scope="session")
def parameters() -> BSPBalancingOrdersParameters:
    return BSPBalancingOrdersParameters.model_validate(PARAMETERS_DICT)


@pytest.fixture(scope="session")
def time_index(parameters) -> list:
    return generate_datetimes(
        parameters.temporal.start_date,
        parameters.temporal.end_date - parameters.temporal.timestep,
        parameters.temporal.timestep,
    )


@pytest.fixture(scope="function")
def mock_timeseries():
    """Return a factory that creates a mock Timeseries with a fixed get_value."""

    def _make(value: float = 0.0):
        ts = MagicMock()
        ts.get_value = MagicMock(return_value=value)
        ts.__sub__ = MagicMock(side_effect=lambda other: _make(value - other.get_value(None)))
        ts.__add__ = MagicMock(side_effect=lambda other: _make(value + other.get_value(None)))
        return ts

    return _make


@pytest.fixture(scope="function")
def mock_forecasting_matrix(mock_timeseries):
    """Return a factory that creates a mock ForecastingMatrix returning a fixed Timeseries."""

    def _make(value: float = 0.0):
        fm = MagicMock()
        fm.get_forecast = MagicMock(return_value=mock_timeseries(value))
        return fm

    return _make


@pytest.fixture(scope="session")
def real_market_objects():
    """Return real BusinessModel instances required by Order validation."""
    control_block = ControlBlock(name="test_control_block")
    market_area = MarketArea(name="test_market_area", control_block=control_block)
    node = Node(name="test_node", control_block=control_block, market_area=market_area)
    portfolio = Portfolio(name="test_portfolio", control_block=control_block, market_area=market_area)
    return {"control_block": control_block, "market_area": market_area, "node": node, "portfolio": portfolio}


@pytest.fixture(scope="function")
def mock_equipment(mock_forecasting_matrix, mock_timeseries, real_market_objects):
    """Return a Load instance with mocked timeseries fields required by AbstractOrderFormulator."""
    return Load.model_construct(
        name="test_equipment",
        node=real_market_objects["node"],
        portfolio=real_market_objects["portfolio"],
        setup_delay=0.0,
        maximum_gradient=0.0,
        power=mock_forecasting_matrix(50.0),
        fcr_up_procured=mock_forecasting_matrix(0.0),
        fcr_down_procured=mock_forecasting_matrix(0.0),
        afrr_up_procured=mock_forecasting_matrix(0.0),
        afrr_down_procured=mock_forecasting_matrix(0.0),
        mfrr_up_procured=mock_forecasting_matrix(0.0),
        mfrr_down_procured=mock_forecasting_matrix(0.0),
        rr_up_procured=mock_forecasting_matrix(0.0),
        rr_down_procured=mock_forecasting_matrix(0.0),
        variable_cost=mock_timeseries(10.0),
    )
