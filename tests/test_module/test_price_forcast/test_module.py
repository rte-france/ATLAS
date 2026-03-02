import unittest

import pendulum

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.input_loader import load_from_directory
from atlas.modules.price_forcast.price_forcast_input_dataset import PriceForcastInputDataset
from atlas.modules.price_forcast.price_forcast_orchestrator import PriceForcastOrchestrator
from atlas.modules.price_forcast.price_forcast_output_dataset import PriceForcastOutputDataset
from atlas.modules.price_forcast.price_forcast_parameters import PriceForcastParameters


class TestModule(unittest.TestCase):

    def test_module_execution(self):
        data = AtlasDataset.from_directory("test_data/id_price_forecast_input")

        parameter = PriceForcastParameters(
            start_date=pendulum.datetime(2028, 9, 27),
            end_date=pendulum.datetime(2028, 9, 28),
            execution_date=pendulum.datetime(2028, 9, 26, 22),
            timestep="1h",
        )

        input = PriceForcastInputDataset(data, parameter)
        orchestrator = PriceForcastOrchestrator(parameter, input)
        output = orchestrator.execute()
        expected_data = AtlasDataset.from_directory("test_data/id_price_forecast_output")

        assert len(output.market_area) == len(expected_data.market_area)
        for market_area in output.market_area:
            assert (
                market_area.id_price_forecast == expected_data.market_area.get(market_area.name).id_price_forecast
            )
