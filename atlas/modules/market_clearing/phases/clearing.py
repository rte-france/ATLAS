"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from typing import Any

from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases.clearing_model import ClearingModel


class Clearing:

    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.model = None

    def create_model(self):
        self.model = ClearingModel(self.input_dataset, self.parameters)

    def run(self):
        pass

    # Retrieve information after optimization
    # REMIND : nb_saturations may be retrieved with retrieve_critical_branches_saturation_value and allowed_round_off_error
    def retrieve_critical_branches_saturation_value(self) -> dict[str: list[float]]:
        """

        :return: A dictionary containing list of constraint value if the critical branches for each timestep
        :rtype: dict[str: list[float]]
        """
        pass

    def retrieve_accepted_powers(self) -> dict[str, dict[str, float]]:
        """

        :return: A dictionary containing the accepted amounts of power for each orders of each market area
        :rtype: dict[str, dict[str, float]]
        """
        pass

    def retrieve_orders_status(self) -> dict[str, float]:
        """

        :return: A dictionary containing the acceptance status of all orders of each market area
        :rtype: dict[str, dict[str, float]]
        """
        pass

    def retrieve_local_balances(self) -> dict[str, list[float]]:
        """

        :return: A dictionary containing the local balances of each market area for each timestep
        :rtype: dict[str, list[float]]
        """
        pass

    def retrieve_borders_exchanges(self) -> dict[str, list[float]]:
        """

        :return: A dictionary containing the exchange of each border for each timestep
        :rtype: dict[str, list[float]]
        """
        pass

    def retrieve_borders_imports(self) -> dict[str, list[float]]:
        """

        :return: A dictionary containing the import of each border for each timestep
        :rtype: dict[str, list[float]]
        """
        pass

    def retrieve_borders_exports(self) -> dict[str, list[float]]:
        """

        :return: A dictionary containing the export of each border for each timestep
        :rtype: dict[str, list[float]]
        """
        pass

    def retrieve_borders_xsis(self) -> dict[str, list[float]]:
        """

        :return: A dictionary containing the xsis of each border for each timestep
        :rtype: dict[str, list[float]]
        """
        pass

    def retrieve_borders_nus(self) -> dict[str, list[float]]:
        """

        :return: A dictionary containing the nus of each border for each timestep
        :rtype: dict[str, list[float]]
        """
        pass