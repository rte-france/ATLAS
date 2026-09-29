import time
from pathlib import Path

import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.intraday_price_forecast.module import IntradayPriceForecastModule
from tests.utils import check_execution_time

INPUT_DIR = Path("tests/dataset/intraday/intraday_price_forecast_input")
PARAMETERS_PATH = Path("tests/dataset/parameters/intraday/intraday_price_forecast.yml")


@pytest.mark.perf
def test_execution_time_within_threshold():
    module = IntradayPriceForecastModule()
    parameters = module.import_parameters(PARAMETERS_PATH)
    input_data = AtlasDataset.from_directory(INPUT_DIR)

    start = time.perf_counter()
    module.run(input_data, parameters)
    elapsed = time.perf_counter() - start

    check_execution_time("IntradayPriceForecast", elapsed, "IntradayPriceForecast")
