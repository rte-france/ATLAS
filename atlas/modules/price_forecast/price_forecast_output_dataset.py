import copy

from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas.modules.price_forecast.models.market_area import MarketAreaIDPF
from atlas.modules.price_forecast.price_forecast_input_dataset import PriceForecastInputDataset
from atlas.modules.price_forecast.price_forecast_parameters import PriceForecastParameters
from atlas.workflow.change_set import ChangeSet


class PriceForecastOutputDataset(AbstractModuleOutput[PriceForecastParameters]):
    def __init__(self, parameters: PriceForecastParameters, input_dataset: PriceForecastInputDataset):
        self.parameters: PriceForecastParameters = copy.deepcopy(parameters)
        self.input_data = input_dataset

        self.market_area: list[MarketAreaIDPF] = input_dataset.market_area

    def build_change_sets(self) -> None:
        for market_area in self.input_data.market_area:
            self.change_sets.append(ChangeSet.from_object(market_area))
