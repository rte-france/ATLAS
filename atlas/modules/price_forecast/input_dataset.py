from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.price_forecast.models.load import LoadIDPF
from atlas.modules.price_forecast.models.market_area import MarketAreaIDPF
from atlas.modules.price_forecast.models.solar import SolarIDPF
from atlas.modules.price_forecast.models.wind import WindIDPF
from atlas.modules.price_forecast.parameters import PriceForecastParameters


class PriceForecastInputDataset(AbstractDataset[PriceForecastParameters]):
    def __init__(self, raw_data: AtlasDataset, parameters: PriceForecastParameters):
        self.parameters: PriceForecastParameters = parameters
        self.input_data = raw_data

        self.market_area: list[MarketAreaIDPF] = [MarketAreaIDPF(**dict(obj)) for obj in raw_data.market_area]
        self.solar: list[SolarIDPF] = [SolarIDPF(**dict(obj)) for obj in raw_data.solar]
        self.wind: list[WindIDPF] = [WindIDPF(**dict(obj)) for obj in raw_data.wind]
        self.load: list[LoadIDPF] = [LoadIDPF(**dict(obj)) for obj in raw_data.load]
