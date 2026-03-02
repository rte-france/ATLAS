import unittest

import pendulum

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.price_forecast.price_forecast_input_dataset import PriceForcastInputDataset
from atlas.modules.price_forecast.price_forecast_orchestrator import PriceForecastOrchestrator
from atlas.modules.price_forecast.price_forecast_parameters import PriceForecastParameters


class TestModule(unittest.TestCase):

    def test_module_execution(self):
        pass