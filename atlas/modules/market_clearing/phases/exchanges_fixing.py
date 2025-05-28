from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters


class ExchangesFixing:

    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.exchange_fixing = None

    def create_exchange_fixing_model(self):
        pass

    def run(self):
        pass

    def retrieve_borders_exchanges(self) -> dict[str, list[float]]:
        """

        :return: A dictionary containing the exchange of each border for each timestep
        :rtype: dict[str, list[float]]
        """
        pass

    def retrieve_borders_imports(self) -> dict[str, list[float]]:
        """ Only available if there is border with loss and atc model

        :return: A dictionary containing the import of each border for each timestep
        :rtype: dict[str, list[float]]
        """
        pass

    def retrieve_borders_exports(self) -> dict[str, list[float]]:
        """ Only available if there is border with loss and atc model

        :return: A dictionary containing the export of each border for each timestep
        :rtype: dict[str, list[float]]
        """
        pass

    def retrieve_borders_xsis(self) -> dict[str, list[float]]:
        """ Only available if there is border with loss and atc model

        :return: A dictionary containing the xsis of each border for each timestep
        :rtype: dict[str, list[float]]
        """
        pass

    def retrieve_borders_nus(self) -> dict[str, list[float]]:
        """ Only available if there is border with loss and atc model

        :return: A dictionary containing the nus of each border for each timestep
        :rtype: dict[str, list[float]]
        """
        pass