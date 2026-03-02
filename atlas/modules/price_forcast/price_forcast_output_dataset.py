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
from atlas.modules.price_forcast.price_forcast_input_dataset import PriceForcastInputDataset
from atlas.modules.price_forcast.price_forcast_parameters import PriceForcastParameters


class PriceForcastOutputDataset(AbstractDataset[PriceForcastParameters]):
    def __init__(self,
                 parameters: PriceForcastParameters,
                 input_dataset: PriceForcastInputDataset):

        self.parameters: PriceForcastParameters = copy.deepcopy(parameters)

        market_area: list[MarketArea] = copy.deepcopy(input_dataset.market_area)
        self.market_area: list[MarketAreaIDPF] = [cast(MarketAreaIDPF, obj) for obj in market_area]
        input_load: list[Load] = copy.deepcopy(input_dataset.load)
        self.load: list[LoadIDPF] = [cast(LoadIDPF, obj) for obj in input_load]
        input_solar: list[Solar] = copy.deepcopy(input_dataset.solar)
        self.solar: list[SolarIDPF] = [cast(SolarIDPF, obj) for obj in input_solar]
        input_wind: list[Wind] = copy.deepcopy(input_dataset.wind)
        self.wind: list[WindIDPF] = [cast(WindIDPF, obj) for obj in input_wind]

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
