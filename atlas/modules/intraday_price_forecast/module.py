from loguru import logger

from atlas.abstract_class.abstract_module import AbstractModule
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.intraday_price_forecast.input_dataset import IntradayPriceForecastInputDataset
from atlas.modules.intraday_price_forecast.orchestrator import IntradayPriceForecastOrchestrator
from atlas.modules.intraday_price_forecast.output_dataset import IntradayPriceForecastOutputDataset
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters


class IntradayPriceForecastModule(
    AbstractModule[
        IntradayPriceForecastParameters, IntradayPriceForecastInputDataset, IntradayPriceForecastOutputDataset
    ]
):
    def get_parameters_class(self):
        """
        Returns the concrete Parameters class for this module.

        :return: The parameters class for this module
        :rtype: type[IntradayPriceForecastParameters]
        """
        return IntradayPriceForecastParameters

    def import_data(
        self, input_data: AtlasDataset, parameters: IntradayPriceForecastParameters
    ) -> IntradayPriceForecastInputDataset:
        """
        Imports data using business objects and parameters.

        :param input_data: Input data containing business objects
        :type input_data: AtlasDataset
        :param parameters: Module parameters
        :type parameters: IntradayPriceForecastParameters
        :return: Input dataset for the module
        :rtype: IntradayPriceForecastInputDataset
        """
        input_dataset = IntradayPriceForecastInputDataset(input_data, parameters)
        return input_dataset

    def validate_data(
        self, parameters: IntradayPriceForecastParameters, input_dataset: IntradayPriceForecastInputDataset
    ) -> bool:
        return True

    def execute(
        self, parameters: IntradayPriceForecastParameters, input_dataset: IntradayPriceForecastInputDataset
    ) -> IntradayPriceForecastOutputDataset:
        """
        Executes the module's main logic.

        :param parameters: Module parameters
        :type parameters: IntradayPriceForecastParameters
        :param input_dataset: Input dataset
        :type input_dataset: IntradayPriceForecastInputDataset
        :return: Output dataset with computed results
        :rtype: IntradayPriceForecastOutputDataset
        """
        orchestrator = IntradayPriceForecastOrchestrator(parameters, input_dataset)
        output_dataset = orchestrator.execute()
        return output_dataset

    def validates_results(
        self,
        parameters: IntradayPriceForecastParameters,
        input_dataset: IntradayPriceForecastInputDataset,
        output_dataset: IntradayPriceForecastOutputDataset,
    ) -> bool:
        """
        Validates results.

        :param parameters: Module parameters
        :type parameters: IntradayPriceForecastParameters
        :param input_dataset: Input dataset
        :type input_dataset: IntradayPriceForecastInputDataset
        :param output_dataset: Output dataset
        :type output_dataset: IntradayPriceForecastOutputDataset
        :return: True if results are valid, False otherwise
        :rtype: bool
        """
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
        """
        Exports results.

        :param parameters: Module parameters
        :type parameters: IntradayPriceForecastParameters
        :param input_dataset: Input dataset
        :type input_dataset: IntradayPriceForecastInputDataset
        :param output_dataset: Output dataset
        :type output_dataset: IntradayPriceForecastOutputDataset
        """
        return
