"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.models.business_model import BusinessModel
from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters


class MarketClearingOutputDataset(AbstractDataset[MarketClearingParameters]):
    """Output dataset for Market Clearing module
    What to we need from MarketClearing result :
      - accepted_powers
      - local_balances
      - border_exchanges
      - market_prices

    Updated values are :
    - MarketArea :
      - DABalance
      - DAPrice
      - TotalIDBalance
      - IDBalance
      - IDPrice
      - RRActivationPrice
      - RRActivationBalance
      - MFRRActivationPrice
      - MFRRActivationBalance
      - AFRRActivationPrice
      - FCRActivationPrice
    - MarketBorder :
      - DAFlow
      - DAShadowPrice
      - TotalIDFlow
      - IDFlow
      - IDShadowPrice
      - MFRRUpProcurement
      - MFRRDownProcurement
      - AFRRUpProcurement
      - AFRRDownProcurement
      - RRUpProcurement
      - RRDownProcurement
      - RRActivated
      - MFRRActivated
      - AFRRActivated
      - FCRActivated
      - ReferenceFlow
    - CriticalBranch :
      - DAFlow
      - DAShadowPrice
      - TotalIDFlow
      - IDFlow
      - IDShadowPrice
      - MFRRUpProcurement
      - MFRRDownProcurement
      - AFRRUpProcurement
      - AFRRDownProcurement
      - RRUpProcurement
      - RRDownProcurement
      - RRActivated
      - MFRRActivated
      - AFRRActivated
      - FCRActivated
      - ReferenceFlow
    - Order :
      - accepted_power
      - IndividualSpread
    - Equipment :
      - DAClearedQuantity
      - TotalIDClearedQuantity
      - IDClearedQuantity
      - AFRRUpProcured
      - AFRRDownProcured
      - MFRRUpProcured
      - MFRRDownProcured
      - RRUpProcured
      - RRDownProcured
      - RRActivated
      - MFRRActivated
      - AFRRActivated
      - FCRActivated
    - Portfolio :
      - DAClearedQuantity
      - AFRRUpProcured
      - AFRRDownProcured
      - MFRRUpProcured
      - MFRRDownProcured
      - RRUpProcured
      - RRDownProcured
      - RRActivated
      - MFRRActivated
      - AFRRActivated
      - FCRActivated

    """

    def __init__(self, input_dataset: MarketClearingInputDataset):
        self.input_dataset = input_dataset

    def update_dataset(self):
        print()



    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
