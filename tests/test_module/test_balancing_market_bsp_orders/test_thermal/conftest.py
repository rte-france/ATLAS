"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.objects.equipment.thermal import Thermal
from tests.test_module.test_balancing_market_bsp_orders.conftest import make_forecasting_matrix, make_timeseries


@pytest.fixture(scope="function")
def thermal_equipment(parameters, real_market_objects):
    """
    A thermal equipment running mid-range (power=50, between min_power=20 and
    max_power=100), with gradient, procured reserves, and all duration-based
    constraints (setup_delay, minimum_time_on/off, minimum_stable_power_duration,
    startup_duration) disabled by default. Individual tests override whichever
    field they need via object.__setattr__, matching the existing wind/solar
    fixture convention.
    """
    return Thermal.model_construct(
        name="test_thermal",
        node=real_market_objects["node"],
        portfolio=real_market_objects["portfolio"],
        setup_delay=0.0,
        maximum_gradient=0.0,
        power=make_forecasting_matrix(parameters, 50.0),
        maximum_power=make_timeseries(parameters, 100.0),
        minimum_power=make_timeseries(parameters, 20.0),
        variable_cost=make_timeseries(parameters, 80.0),
        startup_cost=make_timeseries(parameters, 500.0),
        fcr_up_procured=make_forecasting_matrix(parameters, 0.0),
        fcr_down_procured=make_forecasting_matrix(parameters, 0.0),
        afrr_up_procured=make_forecasting_matrix(parameters, 0.0),
        afrr_down_procured=make_forecasting_matrix(parameters, 0.0),
        mfrr_up_procured=make_forecasting_matrix(parameters, 0.0),
        mfrr_down_procured=make_forecasting_matrix(parameters, 0.0),
        rr_up_procured=make_forecasting_matrix(parameters, 0.0),
        rr_down_procured=make_forecasting_matrix(parameters, 0.0),
        minimum_time_on=pendulum.duration(minutes=0),
        minimum_time_off=pendulum.duration(minutes=0),
        minimum_stable_power_duration=pendulum.duration(minutes=0),
        startup_duration=pendulum.duration(minutes=0),
    )
