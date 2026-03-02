from typing import cast

from atlas import (
    BusinessModel,
    Load,
    MarketArea,
    Solar,
    Wind,
    AtlasDataset,
)
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.config import INVERSE_MODEL_MAPPING_NAME
from atlas.modules.price_forcast.data_models.load import LoadIDPF
from atlas.modules.price_forcast.data_models.market_area import MarketAreaIDPF
from atlas.modules.price_forcast.data_models.solar import SolarIDPF
from atlas.modules.price_forcast.data_models.wind import WindIDPF
from atlas.modules.price_forcast.price_forcast_parameters import PriceForcastParameters


class PriceForcastInputDataset(AbstractDataset[PriceForcastParameters]):
    def __init__(self, raw_data: AtlasDataset, parameters: PriceForcastParameters):
        self.parameters: PriceForcastParameters = parameters
        self.input_data = raw_data

        self.market_area: list[MarketAreaIDPF] = [cast(MarketAreaIDPF, obj) for obj in raw_data.market_area]
        self.solar: list[SolarIDPF] = [cast(SolarIDPF, obj) for obj in raw_data.solar]
        self.wind: list[WindIDPF] = [cast(WindIDPF, obj) for obj in raw_data.wind]
        self.load: list[Load] = [cast(LoadIDPF, obj) for obj in raw_data.load]

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
