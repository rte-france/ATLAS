"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.abstract_module import AbstractModule
from atlas.models.business_model import BusinessModel
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.output_dataset import MarketClearingOutputDataset
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases.clearing import Clearing
from atlas.modules.market_clearing.phases.exchanges_fixing import ExchangesFixing
from atlas.modules.market_clearing.phases.marginal_fixing import MarginalFixing
from atlas.modules.market_clearing.phases.market_clearing_results import MarketClearingResults
from atlas.modules.market_clearing.phases.pricing import Pricing


class MarketClearingModule(
    AbstractModule[MarketClearingParameters, MarketClearingInputDataset, MarketClearingOutputDataset]
):
    """The Market Clearing prototype, resulting from a merge of TERRE and Optimate's Market Coupling module, deals with
    the clearing of short-term markets of electricity at the European scale.
    """

    def get_parameters_class(self):
        """Returns the concrete Parameters class for this module."""
        return MarketClearingParameters

    def import_data(
        self, raw_data: dict[str, list[type[BusinessModel]]], parameters: MarketClearingParameters
    ) -> MarketClearingInputDataset:
        input_dataset = MarketClearingInputDataset(raw_data, parameters)
        return input_dataset

    def validate_data(self, parameters: MarketClearingParameters, input_dataset: MarketClearingInputDataset) -> bool:
        return True

    def execute(
        self, parameters: MarketClearingParameters, input_dataset: MarketClearingInputDataset
    ) -> MarketClearingOutputDataset:
        clearing = Clearing(input_dataset, parameters)
        clearing.run()
        saturated_critical_branches = clearing.retrieve_saturated_critical_branch()
        local_balances = clearing.retrieve_local_balances()
        accepted_powers = clearing.retrieve_accepted_powers()

        # Launch Exchange Fixing phase
        exchange_fixing = ExchangesFixing(input_dataset, parameters)
        exchange_fixing.run(local_balances)
        border_exchanges = exchange_fixing.retrieve_border_exchanges()

        # Launch Pricing phase
        pricing = Pricing(
            input_dataset, parameters, saturated_critical_branches, border_exchanges, local_balances, accepted_powers
        )
        pricing.run()
        market_prices = pricing.retrieve_market_prices()

        # Launch Marginal Fixing phase
        marginal_fixing = MarginalFixing(input_dataset, parameters)
        marginal_fixing.run(accepted_powers, market_prices)

        market_clearing_output_dataset = MarketClearingOutputDataset(input_dataset)
        market_clearing_output_dataset.run(accepted_powers, local_balances, border_exchanges, market_prices)

        return market_clearing_output_dataset

    def validates_results(
        self,
        parameters: MarketClearingParameters,
        input_dataset: MarketClearingInputDataset,
        output_dataset: MarketClearingOutputDataset,
    ) -> bool:
        return True

    def export_results(
        self,
        parameters: MarketClearingParameters,
        input_dataset: MarketClearingInputDataset,
        output_dataset: MarketClearingOutputDataset,
    ) -> None:
        market_clearing_result = MarketClearingResults(input_dataset, parameters)
        market_clearing_result.run()
        return
