from atlas import AtlasDataset
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.modules.price_forecast.price_forecast_input_dataset import PriceForcastInputDataset
from atlas.modules.price_forecast.price_forecast_orchestrator import PriceForecastOrchestrator
from atlas.modules.price_forecast.price_forecast_output_dataset import PriceForecastOutputDataset
from atlas.modules.price_forecast.price_forecast_parameters import PriceForecastParameters


class PriceForecastModule(AbstractModule[PriceForecastParameters, PriceForcastInputDataset, PriceForecastOutputDataset]):
    def get_parameters_class(self):
        """Returns the concrete Parameters class for this module."""
        return PriceForecastParameters

    def import_data(self, raw_data: AtlasDataset, parameters: PriceForecastParameters) -> PriceForcastInputDataset:
        """Imports data using business objects and parameters."""
        input_dataset = PriceForcastInputDataset(raw_data, parameters)
        return input_dataset

    def validate_data(self, parameters: PriceForecastParameters, input_dataset: PriceForcastInputDataset) -> bool:
        return True

    def execute(
        self, parameters: PriceForecastParameters, input_dataset: PriceForcastInputDataset
    ) -> PriceForecastOutputDataset:
        """Executes the module's main logic."""
        orchestrator = PriceForecastOrchestrator(parameters, input_dataset)
        output_dataset = orchestrator.execute()
        return output_dataset

    def validates_results(
        self,
        parameters: PriceForecastParameters,
        input_dataset: PriceForcastInputDataset,
        output_dataset: PriceForecastOutputDataset,
    ) -> bool:
        """Validates results"""
        return True

    def export_results(
        self,
        parameters: PriceForecastParameters,
        input_dataset: PriceForcastInputDataset,
        output_dataset: PriceForecastOutputDataset,
    ) -> None:
        """Exports results."""
        return
