"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries


@pytest.fixture
def minimal_forecasting_matrix():
    """Create a minimal ForecastingMatrix for testing."""
    ts = Timeseries.from_index(
        start_date=pendulum.datetime(2024, 1, 1),
        frequency=pendulum.duration(hours=1),
        end_date=pendulum.datetime(2024, 1, 2),
        default_value=50.0,
    )
    fm = ForecastingMatrix()
    fm.add(ts, pendulum.datetime(2024, 1, 1))
    return fm


@pytest.fixture
def minimal_timeseries():
    """Create a minimal Timeseries for testing."""
    return Timeseries.from_index(
        start_date=pendulum.datetime(2024, 1, 1),
        frequency=pendulum.duration(hours=1),
        end_date=pendulum.datetime(2024, 1, 2),
        default_value=50.0,
    )


@pytest.fixture
def minimal_control_block_dict():
    """Create a minimal ControlBlock dictionary for Pydantic validation."""
    return {
        "name": "test_control_block",
    }


@pytest.fixture
def minimal_market_area_dict(minimal_forecasting_matrix, minimal_timeseries, minimal_control_block_dict):
    """Create a minimal MarketArea dictionary for Pydantic validation."""
    return {
        "name": "test_market",
        "control_block": minimal_control_block_dict["name"],
        "price_forecast_medium": minimal_forecasting_matrix,
        "da_price": minimal_timeseries,
    }
