import copy

from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas.modules.intraday_price_forecast.input_dataset import IntradayPriceForecastInputDataset
from atlas.modules.intraday_price_forecast.models.market_area import MarketAreaIDPF
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters
from atlas.workflow.change_set import ChangeSet


class IntradayPriceForecastOutputDataset(AbstractModuleOutput[IntradayPriceForecastParameters]):
    def __init__(self, parameters: IntradayPriceForecastParameters, input_dataset: IntradayPriceForecastInputDataset):
        self.parameters: IntradayPriceForecastParameters = copy.deepcopy(parameters)
        self.input_data = input_dataset

        self.market_area: list[MarketAreaIDPF] = input_dataset.market_area

    def build_change_sets(self) -> None:
        for market_area in self.input_data.market_area:
            self.change_sets.append(ChangeSet.from_object(market_area))
