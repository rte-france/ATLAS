from atlas.abstract_class.dataset import AbstractDataset
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.intraday_price_forecast.input_objects.load import LoadIDPF
from atlas.modules.intraday_price_forecast.input_objects.market_area import MarketAreaIDPF
from atlas.modules.intraday_price_forecast.input_objects.portfolio import PortfolioIDPF
from atlas.modules.intraday_price_forecast.input_objects.solar import SolarIDPF
from atlas.modules.intraday_price_forecast.input_objects.wind import WindIDPF
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters


class IntradayPriceForecastInputDataset(AbstractDataset[IntradayPriceForecastParameters]):
    def __init__(self, input_data: AtlasDataset, parameters: IntradayPriceForecastParameters):
        self.parameters: IntradayPriceForecastParameters = parameters
        self.input_data = input_data

        self.market_area: list[MarketAreaIDPF] = [MarketAreaIDPF(**dict(obj)) for obj in input_data.market_area]

        market_area_map = {ma.name: ma for ma in self.market_area}

        self.solar: list[SolarIDPF] = []
        for solar_obj in input_data.solar:
            solar_dict = dict(solar_obj)
            if solar_obj.portfolio is not None and solar_obj.portfolio.market_area is not None:
                portfolio_dict = dict(solar_obj.portfolio)
                portfolio_dict["market_area"] = market_area_map[solar_obj.portfolio.market_area.name]
                solar_dict["portfolio"] = PortfolioIDPF(**portfolio_dict)
            self.solar.append(SolarIDPF(**solar_dict))

        self.wind: list[WindIDPF] = []
        for wind_obj in input_data.wind:
            wind_dict = dict(wind_obj)
            if wind_obj.portfolio is not None and wind_obj.portfolio.market_area is not None:
                portfolio_dict = dict(wind_obj.portfolio)
                portfolio_dict["market_area"] = market_area_map[wind_obj.portfolio.market_area.name]
                wind_dict["portfolio"] = PortfolioIDPF(**portfolio_dict)
            self.wind.append(WindIDPF(**wind_dict))

        self.load: list[LoadIDPF] = []
        for load_obj in input_data.load:
            load_dict = dict(load_obj)
            if load_obj.portfolio is not None and load_obj.portfolio.market_area is not None:
                portfolio_dict = dict(load_obj.portfolio)
                portfolio_dict["market_area"] = market_area_map[load_obj.portfolio.market_area.name]
                load_dict["portfolio"] = PortfolioIDPF(**portfolio_dict)
            self.load.append(LoadIDPF(**load_dict))
