from atlas.abstract_class.abstract_module import AbstractModule

from atlas import BusinessModel
from atlas.modules.price_forcast.price_forcast_orchestrator import PriceForcastOrchestrator
from atlas.modules.price_forcast.price_forcast_input_dataset import PriceForcastInputDataset
from atlas.modules.price_forcast.price_forcast_output_dataset import PriceForcastOutputDataset
from atlas.modules.price_forcast.price_forcast_parameters import PriceForcastParameters

class MarketClearingModule(
    AbstractModule[PriceForcastParameters, PriceForcastInputDataset, PriceForcastOutputDataset]
):
    def get_parameters_class(self):
        """Returns the concrete Parameters class for this module."""
        return PriceForcastParameters

    def import_data(
        self, raw_data: dict[str, list[type[BusinessModel]]], parameters: PriceForcastParameters
    ) -> PriceForcastInputDataset:
        """Imports data using business objects and parameters."""
        input_dataset = PriceForcastInputDataset(raw_data, parameters)
        return input_dataset

    def validate_data(self, parameters: PriceForcastParameters, input_dataset: PriceForcastInputDataset) -> bool:
        # TODO
        # FIXME fix comment - sont-ils pertinant?
        # Check control block parameters compare to control block object
        # Check market area parameters compare to Market Area object
        # FIXME - May add sub function to make thing more clean
        return True

    def execute(
        self, parameters: PriceForcastParameters, input_dataset: PriceForcastInputDataset
    ) -> PriceForcastOutputDataset:
        """Executes the module's main logic."""
        orchestrator = PriceForcastOrchestrator(parameters, input_dataset)
        output_dataset = orchestrator.execute()
        return output_dataset

    def validates_results(
        self,
        parameters: PriceForcastParameters,
        input_dataset: PriceForcastInputDataset,
        output_dataset: PriceForcastOutputDataset,
    ) -> bool:
        """Validates results"""
        # TODO
        return True

    def export_results(
        self,
        parameters: PriceForcastParameters,
        input_dataset: PriceForcastInputDataset,
        output_dataset: PriceForcastOutputDataset,
    ) -> None:
        """Exports results."""
        # TODO
        return