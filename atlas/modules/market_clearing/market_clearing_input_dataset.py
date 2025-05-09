"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.models.business_model import BusinessModel
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters


class MarketClearingInputDataset(AbstractDataset[MarketClearingParameters]):
    """Input dataset for Market Clearing module"""

    def __init__(self, parameters: MarketClearingParameters):
        self.parameters = parameters
        self.market_areas = None
        self.times = []

    def set_market_areas(self, market_areas) -> None:
        if self.parameters.market == "All":
            self.market_areas = market_areas
        else:
            self.market_areas = [
                market_area for market_area in market_areas if market_area.name in self.parameters.market
            ]

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
