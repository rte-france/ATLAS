import unittest

import pendulum

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.price_forecast.input_dataset import PriceForecastInputDataset
from atlas.modules.price_forecast.orchestrator import PriceForecastOrchestrator
from atlas.modules.price_forecast.parameters import PriceForecastParameters


class TestModule(unittest.TestCase):

    def test_module_execution(self):
        pass