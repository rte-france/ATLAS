"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.container import Container
from atlas.modules.day_ahead_orders.input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling

DAY_AHEAD_INPUT_DIR = Path("tests/dataset/day_ahead_input")
MARKET_CLEARING_INPUT_DIR = Path("tests/dataset/market_clearing_input")

STEPS_PARAMS_DICT = {
    "temporal": {
        "start_date": "2028-09-27 00:00:00",
        "execution_date": "2028-09-26 12:00:00",
        "end_date": "2028-09-28 00:00:00",
        "timestep": "PT1H",
    },
    "load_price": 3000,
    "hydraulic_minimal_fragment_size": 100,
    "price_forecasts_types": ["Medium", "High", "Low"],
}


@pytest.fixture(scope="session")
def steps_parameters() -> DayAheadOrdersParameters:
    return DayAheadOrdersParameters.model_validate(STEPS_PARAMS_DICT)


@pytest.fixture(scope="session")
def day_ahead_atlas_data(steps_parameters) -> AtlasDataset:
    if not DAY_AHEAD_INPUT_DIR.exists():
        pytest.skip(f"Day ahead input dataset not found: {DAY_AHEAD_INPUT_DIR}")
    data = AtlasDataset.from_directory(DAY_AHEAD_INPUT_DIR)
    data.set_frequency_all(steps_parameters.temporal.timestep, inplace=True)
    return data


@pytest.fixture(scope="session")
def market_clearing_atlas_data(steps_parameters) -> AtlasDataset:
    if not MARKET_CLEARING_INPUT_DIR.exists():
        pytest.skip(f"Market clearing input dataset not found: {MARKET_CLEARING_INPUT_DIR}")
    data = AtlasDataset.from_directory(MARKET_CLEARING_INPUT_DIR)
    data.set_frequency_all(steps_parameters.temporal.timestep, inplace=True)
    return data


@pytest.fixture(scope="class")
def steps_input_dataset(day_ahead_atlas_data, steps_parameters) -> DayAheadOrdersInputDataset:
    return DayAheadOrdersInputDataset(day_ahead_atlas_data, steps_parameters)


@pytest.fixture(scope="class")
def steps_output_dataset(steps_input_dataset) -> DayAheadOrdersOutput:
    return DayAheadOrdersOutput(steps_input_dataset)


@pytest.fixture(scope="session")
def expected_orders(market_clearing_atlas_data) -> Container[Order]:
    return market_clearing_atlas_data.order


@pytest.fixture(scope="session")
def expected_couplings(market_clearing_atlas_data) -> Container[OrderCoupling]:
    return market_clearing_atlas_data.order_coupling
