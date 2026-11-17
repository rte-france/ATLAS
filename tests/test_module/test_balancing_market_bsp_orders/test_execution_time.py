import time
from pathlib import Path

import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.balancing_market_bsp_orders.module import BSPBalancingOrdersModule
from tests.utils import check_execution_time

INPUT_DIR = Path("tests/dataset/reserves/bsp_balancing_orders/input")
PARAMETERS_PATH = Path("tests/dataset/parameters/reserves/bsp_balancing_orders.yml")


@pytest.mark.perf
def test_execution_time_within_threshold():
    module = BSPBalancingOrdersModule()
    parameters = module.import_parameters(PARAMETERS_PATH)
    input_data = AtlasDataset.from_directory(INPUT_DIR)

    start = time.perf_counter()
    module.run(input_data, parameters)
    elapsed = time.perf_counter() - start

    check_execution_time("BSPBalancingOrders", elapsed, "BSPBalancingOrders")
