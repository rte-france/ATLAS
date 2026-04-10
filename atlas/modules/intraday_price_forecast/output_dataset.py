from atlas.abstract_class.dataset import AbstractModuleOutput
from atlas.modules.intraday_price_forecast.input_dataset import IntradayPriceForecastInputDataset
from atlas.modules.intraday_price_forecast.models.market_area import MarketAreaIDPF
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters
from atlas.orchestrator.change_set import UpdateObject


class IntradayPriceForecastOutputDataset(AbstractModuleOutput[IntradayPriceForecastParameters]):
    def __init__(self, parameters: IntradayPriceForecastParameters, input_dataset: IntradayPriceForecastInputDataset):
        super().__init__()

        self.market_area: list[MarketAreaIDPF] = input_dataset.market_area

    def build_change_sets(self) -> None:
        for market_area in self.market_area:
            self.change_sets.append(
                UpdateObject(
                    {
                        "name": market_area.name,
                        "id_price_forecast": market_area.id_price_forecast,
                    },
                    type(market_area),
                )
            )
