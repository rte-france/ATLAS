import copy

from atlas.modules.price_forcast.price_forcast_parameters import PriceForcastParameters

from atlas import (
    Load,
    MarketArea,
    Solar,
    Wind,
)
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.models.business_model import BusinessModel

from atlas.modules.price_forcast.price_forcast_input_dataset import PriceForcastInputDataset


class PriceForcastOutputDataset(AbstractDataset[PriceForcastParameters]):
    def __init__(self, parameters: PriceForcastParameters, input_dataset: PriceForcastInputDataset):
        self.parameters: PriceForcastParameters = copy.deepcopy(parameters)

        self.market_area: list[MarketArea] = copy.deepcopy(input_dataset.market_area)
        self.load: list[Load] = copy.deepcopy(input_dataset.load)
        self.solar: list[Solar] = copy.deepcopy(input_dataset.solar)
        self.wind: list[Wind] = copy.deepcopy(input_dataset.wind)

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []