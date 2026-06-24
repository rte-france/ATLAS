"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.container import Container
from atlas.modules.intraday_orders.input_dataset import IntradayOrdersInputDataset
from atlas.modules.intraday_orders.output_dataset import IntradayOrdersOutputDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling

ID_ORDERS_INPUT_DIR = Path("tests/dataset/intraday/intraday_orders_input")
ID_MARKET_CLEARING_INPUT_DIR = Path("tests/dataset/intraday/market_clearing_input")

FORMULATOR_PARAMS_DICT = {
    "temporal": {
        "start_date": "2028-09-27 00:00:00",
        "execution_date": "2028-09-26 12:00:00",
        "end_date": "2028-09-28 00:00:00",
        "timestep": "PT1H",
    },
    "consumption_price": 3000.0,
    "hydraulic_minimal_fragment_size": 150.0,
    "large_imbalance_penalty": 0.2,
    "allowed_round_off_error": 0.001,
    "electric_vehicles_complement_ordering": True,
}


@pytest.fixture(scope="session")
def formulator_parameters() -> IntradayOrdersParameters:
    return IntradayOrdersParameters.model_validate(FORMULATOR_PARAMS_DICT)


@pytest.fixture(scope="session")
def id_orders_atlas_data(formulator_parameters) -> AtlasDataset:
    if not ID_ORDERS_INPUT_DIR.exists():
        pytest.skip(f"Intraday orders input dataset not found: {ID_ORDERS_INPUT_DIR}")
    data = AtlasDataset.from_directory(ID_ORDERS_INPUT_DIR)
    data.set_frequency_all(formulator_parameters.temporal.timestep, inplace=True)
    return data


@pytest.fixture(scope="session")
def id_market_clearing_atlas_data(formulator_parameters) -> AtlasDataset:
    if not ID_MARKET_CLEARING_INPUT_DIR.exists():
        pytest.skip(f"Intraday market clearing input dataset not found: {ID_MARKET_CLEARING_INPUT_DIR}")
    data = AtlasDataset.from_directory(ID_MARKET_CLEARING_INPUT_DIR)
    data.set_frequency_all(formulator_parameters.temporal.timestep, inplace=True)
    return data


@pytest.fixture(scope="class")
def formulator_input_dataset(id_orders_atlas_data) -> IntradayOrdersInputDataset:
    return IntradayOrdersInputDataset(id_orders_atlas_data)


@pytest.fixture(scope="class")
def formulator_output_dataset(formulator_input_dataset) -> IntradayOrdersOutputDataset:
    return IntradayOrdersOutputDataset(formulator_input_dataset)


@pytest.fixture(scope="session")
def expected_orders(id_market_clearing_atlas_data) -> Container[Order]:
    return id_market_clearing_atlas_data.order


@pytest.fixture(scope="session")
def expected_couplings(id_market_clearing_atlas_data) -> Container[OrderCoupling]:
    return id_market_clearing_atlas_data.order_coupling
