from loguru import logger

from atlas import AtlasDataset
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.modules.price_forecast.price_forecast_input_dataset import PriceForecastInputDataset
from atlas.modules.price_forecast.price_forecast_orchestrator import PriceForecastOrchestrator
from atlas.modules.price_forecast.price_forecast_output_dataset import PriceForecastOutputDataset
from atlas.modules.price_forecast.price_forecast_parameters import PriceForecastParameters


class PriceForecastModule(
    AbstractModule[PriceForecastParameters, PriceForecastInputDataset, PriceForecastOutputDataset]
):
    def get_parameters_class(self):
        """Returns the concrete Parameters class for this module."""
        return PriceForecastParameters

    def import_data(self, raw_data: AtlasDataset, parameters: PriceForecastParameters) -> PriceForecastInputDataset:
        """Imports data using business objects and parameters."""
        input_dataset = PriceForecastInputDataset(raw_data, parameters)
        return input_dataset

    def validate_data(self, parameters: PriceForecastParameters, input_dataset: PriceForecastInputDataset) -> bool:
        return True

    def execute(
        self, parameters: PriceForecastParameters, input_dataset: PriceForecastInputDataset
    ) -> PriceForecastOutputDataset:
        """Executes the module's main logic."""
        orchestrator = PriceForecastOrchestrator(parameters, input_dataset)
        output_dataset = orchestrator.execute()
        return output_dataset

    def validates_results(
        self,
        parameters: PriceForecastParameters,
        input_dataset: PriceForecastInputDataset,
        output_dataset: PriceForecastOutputDataset,
    ) -> bool:
        """Validates results"""
        for market_area in output_dataset.market_area:
            if market_area.id_price_forecast is None:
                logger.error(
                    f"intraday price forecast missing for Market area {market_area.name} doesn't have negative price cap isn't negative: {parameters.intraday_negative_price_cap}"
                )
                return False
            if parameters.execution_date not in market_area.id_price_forecast:
                logger.error(
                    f"Missing timestep {parameters.execution_date} in price forecast for Market area {market_area.name}"
                )
                return False
        return True

    def export_results(
        self,
        parameters: PriceForecastParameters,
        input_dataset: PriceForecastInputDataset,
        output_dataset: PriceForecastOutputDataset,
    ) -> None:
        """Exports results."""
        return
