"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from atlas.abstract_class.abstract_module import AbstractModule
from atlas.models.business_model import BusinessModel
from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_output_dataset import MarketClearingOutputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases.clearing import Clearing
from atlas.modules.market_clearing.phases.marginal_fixing import MarginalFixing


class MarketClearingModule(
    AbstractModule[MarketClearingParameters, MarketClearingInputDataset, MarketClearingOutputDataset]
):
    """The Market Clearing prototype, resulting from a merge of TERRE and Optimate's Market Coupling module, deals with
    the clearing of short-term markets of elecricity at the European scale.
    """

    def create_parameters(self, raw_params: dict[str, Any]) -> MarketClearingParameters:
        return MarketClearingParameters(**raw_params)

    def import_data(
        self, raw_data: dict[str, list[type(BusinessModel)]], parameters: MarketClearingParameters
    ) -> MarketClearingInputDataset:
        input_dataset = MarketClearingInputDataset(raw_data, parameters)
        return input_dataset

    def validate_data(self, parameters: MarketClearingParameters, input_dataset: MarketClearingInputDataset) -> bool:
        # Check control block parameters compare to control block object
        # Check market area parameters compare to Market Area object
        return True

    def execute(
        self, parameters: MarketClearingParameters, input_dataset: MarketClearingInputDataset
    ) -> MarketClearingOutputDataset:
        clearing = Clearing(input_dataset, parameters)
        clearing.run()
        # Launch Exchange Fixing phase
        # Launch Pricing phase
        market_prices = {}  # retrieve from pricing
        marginal_fixing = MarginalFixing(input_dataset, parameters)
        marginal_fixing.run(clearing.retrieve_accepted_powers(), market_prices)
        return MarketClearingOutputDataset()

    def validates_results(
        self,
        parameters: MarketClearingParameters,
        input_dataset: MarketClearingInputDataset,
        output_dataset: MarketClearingOutputDataset,
    ) -> bool:
        pass

    def export_results(
        self,
        parameters: MarketClearingParameters,
        input_dataset: MarketClearingInputDataset,
        output_dataset: MarketClearingOutputDataset,
    ) -> None:
        # 4 csv files : borders, coupling_data, offers and market_areas_data
        return
