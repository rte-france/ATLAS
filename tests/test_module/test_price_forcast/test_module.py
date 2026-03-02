import unittest

import pendulum

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.price_forcast.price_forcast_input_dataset import PriceForcastInputDataset
from atlas.modules.price_forcast.price_forcast_orchestrator import PriceForcastOrchestrator
from atlas.modules.price_forcast.price_forcast_parameters import PriceForcastParameters


class TestModule(unittest.TestCase):

    def test_module_execution(self):
        pass