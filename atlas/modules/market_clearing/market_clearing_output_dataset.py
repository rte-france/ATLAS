"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import BusinessModel
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters


class MarketClearingOutputDataset(AbstractDataset[MarketClearingParameters]):
    """Output dataset for Market Clearing module"""

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
