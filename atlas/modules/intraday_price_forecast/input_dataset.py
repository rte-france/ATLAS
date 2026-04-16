from atlas.abstract_class.dataset import AbstractDataset
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.intraday_price_forecast.input_objects.load import LoadIDPF
from atlas.modules.intraday_price_forecast.input_objects.market_area import MarketAreaIDPF
from atlas.modules.intraday_price_forecast.input_objects.solar import SolarIDPF
from atlas.modules.intraday_price_forecast.input_objects.wind import WindIDPF
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters


class IntradayPriceForecastInputDataset(AbstractDataset[IntradayPriceForecastParameters]):
    def __init__(self, input_data: AtlasDataset, parameters: IntradayPriceForecastParameters):
        self.parameters: IntradayPriceForecastParameters = parameters

        self.market_area: list[MarketAreaIDPF] = [MarketAreaIDPF(**dict(obj)) for obj in input_data.market_area]
        self.solar: list[SolarIDPF] = [SolarIDPF(**dict(obj)) for obj in input_data.solar]
        self.wind: list[WindIDPF] = [WindIDPF(**dict(obj)) for obj in input_data.wind]
        self.load: list[LoadIDPF] = [LoadIDPF(**dict(obj)) for obj in input_data.load]
