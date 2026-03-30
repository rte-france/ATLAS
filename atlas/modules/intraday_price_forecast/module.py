from loguru import logger

from atlas.abstract_class.abstract_module import AbstractModule
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.intraday_price_forecast.input_dataset import IntradayPriceForecastInputDataset
from atlas.modules.intraday_price_forecast.orchestrator import PriceForecastOrchestrator
from atlas.modules.intraday_price_forecast.output_dataset import IntradayPriceForecastOutputDataset
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters


class IntradayPriceForecast(
    AbstractModule[
        IntradayPriceForecastParameters, IntradayPriceForecastInputDataset, IntradayPriceForecastOutputDataset
    ]
):
    def get_parameters_class(self):
        """Returns the concrete Parameters class for this module."""
        return IntradayPriceForecastParameters

    def import_data(
        self, input_data: AtlasDataset, parameters: IntradayPriceForecastParameters
    ) -> IntradayPriceForecastInputDataset:
        """Imports data using business objects and parameters."""
        input_dataset = IntradayPriceForecastInputDataset(input_data, parameters)
        return input_dataset

    def validate_data(
        self, parameters: IntradayPriceForecastParameters, input_dataset: IntradayPriceForecastInputDataset
    ) -> bool:
        return True

    def execute(
        self, parameters: IntradayPriceForecastParameters, input_dataset: IntradayPriceForecastInputDataset
    ) -> IntradayPriceForecastOutputDataset:
        """Executes the module's main logic."""
        orchestrator = PriceForecastOrchestrator(parameters, input_dataset)
        output_dataset = orchestrator.execute()
        return output_dataset

    def validates_results(
        self,
        parameters: IntradayPriceForecastParameters,
        input_dataset: IntradayPriceForecastInputDataset,
        output_dataset: IntradayPriceForecastOutputDataset,
    ) -> bool:
        """Validates results"""
        for market_area in output_dataset.market_area:
            if market_area.id_price_forecast is None:
                logger.error(
                    f"intraday price forecast missing for Market area {market_area.name} doesn't have negative price cap isn't negative: {parameters.intraday_negative_price_cap}"
                )
                return False
            if parameters.temporal.execution_date not in market_area.id_price_forecast:
                logger.error(
                    f"Missing timestep {parameters.temporal.execution_date} in price forecast for Market area {market_area.name}"
                )
                return False
        return True

    def export_results(
        self,
        parameters: IntradayPriceForecastParameters,
        input_dataset: IntradayPriceForecastInputDataset,
        output_dataset: IntradayPriceForecastOutputDataset,
    ) -> None:
        """Exports results."""
        return
