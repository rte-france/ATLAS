from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.intraday_price_forecast.models.load import LoadIDPF
from atlas.modules.intraday_price_forecast.models.market_area import MarketAreaIDPF
from atlas.modules.intraday_price_forecast.models.solar import SolarIDPF
from atlas.modules.intraday_price_forecast.models.wind import WindIDPF
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters


class IntradayPriceForecastInputDataset(AbstractDataset[IntradayPriceForecastParameters]):
    def __init__(self, input_data: AtlasDataset, parameters: IntradayPriceForecastParameters):
        self.parameters: IntradayPriceForecastParameters = parameters
        self.input_data = input_data

        self.market_area: list[MarketAreaIDPF] = [MarketAreaIDPF(**dict(obj)) for obj in input_data.market_area]
        self.solar: list[SolarIDPF] = [SolarIDPF(**dict(obj)) for obj in input_data.solar]
        self.wind: list[WindIDPF] = [WindIDPF(**dict(obj)) for obj in input_data.wind]
        self.load: list[LoadIDPF] = [LoadIDPF(**dict(obj)) for obj in input_data.load]
