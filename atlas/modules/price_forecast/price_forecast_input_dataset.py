from typing import cast

from atlas import (
    AtlasDataset,
)
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.modules.price_forecast.data_models.load import LoadIDPF
from atlas.modules.price_forecast.data_models.market_area import MarketAreaIDPF
from atlas.modules.price_forecast.data_models.solar import SolarIDPF
from atlas.modules.price_forecast.data_models.wind import WindIDPF
from atlas.modules.price_forecast.price_forecast_parameters import PriceForecastParameters


class PriceForcastInputDataset(AbstractDataset[PriceForecastParameters]):
    def __init__(self, raw_data: AtlasDataset, parameters: PriceForecastParameters):
        self.parameters: PriceForecastParameters = parameters
        self.input_data = raw_data

        self.market_area: list[MarketAreaIDPF] = [cast(MarketAreaIDPF, obj) for obj in raw_data.market_area]
        self.solar: list[SolarIDPF] = [cast(SolarIDPF, obj) for obj in raw_data.solar]
        self.wind: list[WindIDPF] = [cast(WindIDPF, obj) for obj in raw_data.wind]
        self.load: list[LoadIDPF] = [cast(LoadIDPF, obj) for obj in raw_data.load]
