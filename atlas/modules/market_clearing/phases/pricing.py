from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters


class Pricing:
    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.first_pricing = None
        self.second_pricing = None
        self.third_pricing = None

    def create_first_pricing_model(self):
        pass

    def create_second_pricing_model(self):
        pass

    def create_third_pricing_model(self):
        pass

    def run(self):
        pass

    def retrieve_market_prices(self) -> dict[str, list[float]]:
        """

        :return: A dictionary containing the market price of each market area for each timestep
        :rtype: dict[str, list[float]]
        """
        pass
