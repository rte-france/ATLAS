"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest

from atlas.timing import generate_datetimes
from atlas.enums import MarketType
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
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


@pytest.fixture(scope="function")
def parameters() -> BSPBalancingOrdersParameters:
    return BSPBalancingOrdersParameters.model_validate(PARAMETERS_DICT)


@pytest.fixture(scope="function")
def parameters_self_balancing() -> BSPBalancingOrdersParameters:
    return BSPBalancingOrdersParameters.model_validate({**PARAMETERS_DICT, "res_self_balancing": True})


@pytest.fixture(scope="function")
def time_index(parameters) -> list:
    return generate_datetimes(
        parameters.temporal.start_date,
        parameters.temporal.end_date - parameters.temporal.timestep,
        parameters.temporal.timestep,
    )


@pytest.fixture(scope="session")
def real_market_objects():
    """Return real BusinessModel instances required by Order validation."""
    control_block = ControlBlock(name="test_control_block")
    market_area = MarketArea(name="test_market_area", control_block=control_block)
    node = Node(name="test_node", control_block=control_block, market_area=market_area)
    portfolio = Portfolio(name="test_portfolio", control_block=control_block, market_area=market_area)
    return {"control_block": control_block, "market_area": market_area, "node": node, "portfolio": portfolio}


def make_forecasting_matrix(parameters: BSPBalancingOrdersParameters, value: float) -> ForecastingMatrix:
    """
    Build a ForecastingMatrix with a single forecast at execution_date covering the full time frame.

    :param parameters: Module parameters providing temporal context
    :type parameters: BSPBalancingOrdersParameters
    :param value: Constant value to fill the timeseries with
    :type value: float
    :return: A ForecastingMatrix with one forecast entry
    :rtype: ForecastingMatrix
    """
    ts = Timeseries.from_index(
        start_date=parameters.temporal.start_date,
        frequency=parameters.temporal.timestep,
        end_date=parameters.temporal.end_date,
        default_value=value,
    )
    fm = ForecastingMatrix()
    fm.add(ts, parameters.temporal.execution_date)
    return fm


def make_timeseries(parameters: BSPBalancingOrdersParameters, value: float) -> Timeseries:
    """
    Build a Timeseries covering the full time frame with a constant value.

    :param parameters: Module parameters providing temporal context
    :type parameters: BSPBalancingOrdersParameters
    :param value: Constant value to fill the timeseries with
    :type value: float
    :return: A Timeseries with constant values
    :rtype: Timeseries
    """
    return Timeseries.from_index(
        start_date=parameters.temporal.start_date,
        frequency=parameters.temporal.timestep,
        end_date=parameters.temporal.end_date,
        default_value=value,
    )


@pytest.fixture(scope="function")
def mock_equipment(parameters, real_market_objects):
    """Return a Load instance with real timeseries fields required by AbstractOrderFormulator."""
    return Load.model_construct(
        name="test_equipment",
        node=real_market_objects["node"],
        portfolio=real_market_objects["portfolio"],
        setup_delay=0.0,
        maximum_gradient=0.0,
        power=make_forecasting_matrix(parameters, 50.0),
        fcr_up_procured=make_forecasting_matrix(parameters, 0.0),
        fcr_down_procured=make_forecasting_matrix(parameters, 0.0),
        afrr_up_procured=make_forecasting_matrix(parameters, 0.0),
        afrr_down_procured=make_forecasting_matrix(parameters, 0.0),
        mfrr_up_procured=make_forecasting_matrix(parameters, 0.0),
        mfrr_down_procured=make_forecasting_matrix(parameters, 0.0),
        rr_up_procured=make_forecasting_matrix(parameters, 0.0),
        rr_down_procured=make_forecasting_matrix(parameters, 0.0),
        variable_cost=make_timeseries(parameters, 10.0),
        maximum_power_forecast=make_forecasting_matrix(parameters, 100.0),
    )
