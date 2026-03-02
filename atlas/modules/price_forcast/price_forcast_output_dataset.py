import copy
from typing import cast

from atlas import (
    Load,
    MarketArea,
    Solar,
    Wind,
)
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.models.business_model import BusinessModel
from atlas.modules.price_forcast.data_models.load import LoadIDPF
from atlas.modules.price_forcast.data_models.market_area import MarketAreaIDPF
from atlas.modules.price_forcast.data_models.solar import SolarIDPF
from atlas.modules.price_forcast.data_models.wind import WindIDPF
from atlas.modules.price_forcast.price_forcast_input_dataset import PriceForcastInputDataset
from atlas.modules.price_forcast.price_forcast_parameters import PriceForcastParameters


class PriceForcastOutputDataset(AbstractDataset[PriceForcastParameters]):
    def __init__(self, parameters: PriceForcastParameters, input_dataset: PriceForcastInputDataset):
        self.parameters: PriceForcastParameters = copy.deepcopy(parameters)

        self.market_area = copy.deepcopy(input_dataset.market_area)
        self.load = copy.deepcopy(input_dataset.load)
        self.solar = copy.deepcopy(input_dataset.solar)
        self.wind = copy.deepcopy(input_dataset.wind)

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
