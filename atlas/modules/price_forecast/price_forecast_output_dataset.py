import copy

from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas.modules.price_forecast.data_models.load import LoadIDPF
from atlas.modules.price_forecast.data_models.market_area import MarketAreaIDPF
from atlas.modules.price_forecast.data_models.solar import SolarIDPF
from atlas.modules.price_forecast.data_models.wind import WindIDPF
from atlas.modules.price_forecast.price_forecast_input_dataset import PriceForcastInputDataset
from atlas.modules.price_forecast.price_forecast_parameters import PriceForecastParameters
from atlas.workflow.change_set import ChangeSet


class PriceForecastOutputDataset(AbstractModuleOutput[PriceForecastParameters]):
    def __init__(self, parameters: PriceForecastParameters, input_dataset: PriceForcastInputDataset):
        self.parameters: PriceForecastParameters = copy.deepcopy(parameters)
        self.input_data = input_dataset

        self.market_area: list[MarketAreaIDPF] = copy.deepcopy(input_dataset.market_area)
        self.load: list[LoadIDPF] = copy.deepcopy(input_dataset.load)
        self.solar: list[SolarIDPF] = copy.deepcopy(input_dataset.solar)
        self.wind: list[WindIDPF] = copy.deepcopy(input_dataset.wind)

    def build_change_sets(self) -> None:
        change_set: ChangeSet = ChangeSet("market_area")
        self.change_sets.append(change_set)
