from atlas import AtlasDataset
from atlas.abstract_class.module import AbstractModule
from atlas.modules.price_forecast_orders_creation.input_dataset import PriceForecastOrdersCreationInputDataset
from atlas.modules.price_forecast_orders_creation.parameters import PriceForecastOrdersCreationParameters
from atlas.modules.price_forecast_orders_creation.result import PriceForecastOrdersCreationResult


class DayAheadOrdersModule(
    AbstractModule[
        PriceForecastOrdersCreationParameters,
        PriceForecastOrdersCreationInputDataset,
        PriceForecastOrdersCreationResult,
    ]
):
    @classmethod
    def get_parameters_class(cls) -> type[PriceForecastOrdersCreationParameters]:
        return PriceForecastOrdersCreationParameters

    def import_data(
        self, input_data: AtlasDataset, parameters: PriceForecastOrdersCreationParameters
    ) -> PriceForecastOrdersCreationInputDataset:
        """Imports data using business objects and parameters."""
        pass

    def validate_data(
        self, parameters: PriceForecastOrdersCreationParameters, input_dataset: PriceForecastOrdersCreationInputDataset
    ) -> bool:
        """Validates imported or generated data."""
        pass

    def validates_results(
        self,
        parameters: PriceForecastOrdersCreationParameters,
        input_dataset: PriceForecastOrdersCreationInputDataset,
        result: PriceForecastOrdersCreationResult,
    ) -> bool:
        """Validates results"""
        pass

    def export_results(
        self,
        parameters: PriceForecastOrdersCreationParameters,
        input_dataset: PriceForecastOrdersCreationInputDataset,
        result: PriceForecastOrdersCreationResult,
    ) -> None:
        """Exports results."""
        pass

    def execute(
        self, parameters: PriceForecastOrdersCreationParameters, input_dataset: PriceForecastOrdersCreationInputDataset
    ) -> PriceForecastOrdersCreationResult:
        """Executes the module's main logic."""
        pass
