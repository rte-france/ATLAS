
from atlas.modules.price_forcast.price_forcast_parameters import PriceForcastParameters

from typing import cast
from atlas import (
    Load,
    MarketArea,
    Solar,
    Wind,
)
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.config import INVERSE_MODEL_MAPPING_NAME
from atlas import BusinessModel


class PriceForcastInputDataset(AbstractDataset[PriceForcastParameters]):
    def __init__(self, raw_data: dict[str, list[type[BusinessModel]]], parameters: PriceForcastParameters):
        self.parameters: PriceForcastParameters = parameters

        self.market_area: list[MarketArea] = (
            [cast(MarketArea, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[MarketArea]]]
            if INVERSE_MODEL_MAPPING_NAME[MarketArea] in raw_data
            else []
        )
        self.solar: list[Solar] = (
            [cast(Solar, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[Solar]]]
            if INVERSE_MODEL_MAPPING_NAME[Solar] in raw_data
            else []
        )
        self.wind: list[Wind] = (
            [cast(Wind, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[Wind]]]
            if INVERSE_MODEL_MAPPING_NAME[Wind] in raw_data
            else []
        )
        self.load: list[Load] = (
            [cast(Load, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[Load]]]
            if INVERSE_MODEL_MAPPING_NAME[Load] in raw_data
            else []
        )

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
