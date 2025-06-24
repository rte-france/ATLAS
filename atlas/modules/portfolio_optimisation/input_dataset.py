"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import (
    BusinessModel,
    ControlBlock,
    Hydro,
    Load,
    MarketArea,
    MarketBorder,
    Node,
    Order,
    OrderCoupling,
    OtherNonDispatchable,
    Portfolio,
    Solar,
    Storage,
    Thermal,
    Wind,
)
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.config import INVERSE_MODEL_MAPPING_NAME
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class PortfolioOptimisationInputDataset(AbstractDataset[PortfolioOptimisationParameters]):
    def __init__(
        self,
        input_data: dict[str, list[BusinessModel]],
        parameters: PortfolioOptimisationParameters,
    ):
        self.input_data = input_data
        self.parameters = parameters

        self.control_block: list[ControlBlock] = input_data[INVERSE_MODEL_MAPPING_NAME[ControlBlock]]
        self.market_area: list[MarketArea] = input_data[INVERSE_MODEL_MAPPING_NAME[MarketArea]]
        self.market_border: list[MarketBorder] = input_data[INVERSE_MODEL_MAPPING_NAME[MarketBorder]]
        self.node: list[Node] = input_data[INVERSE_MODEL_MAPPING_NAME[Node]]
        self.portfolio: list[Portfolio] = input_data[INVERSE_MODEL_MAPPING_NAME[Portfolio]]
        self.wind: list[Wind] = input_data[INVERSE_MODEL_MAPPING_NAME[Wind]]
        self.storage: list[Storage] = input_data[INVERSE_MODEL_MAPPING_NAME[Storage]]
        self.hydro: list[Hydro] = input_data[INVERSE_MODEL_MAPPING_NAME[Hydro]]
        self.solar: list[Solar] = input_data[INVERSE_MODEL_MAPPING_NAME[Solar]]
        self.thermal: list[Thermal] = input_data[INVERSE_MODEL_MAPPING_NAME[Thermal]]
        self.other_non_dispatchable: list[OtherNonDispatchable] = input_data[
            INVERSE_MODEL_MAPPING_NAME[OtherNonDispatchable]
        ]
        self.order: list[Order] = input_data[INVERSE_MODEL_MAPPING_NAME[Order]]
        self.order_coupling: list[OrderCoupling] = input_data[INVERSE_MODEL_MAPPING_NAME[OrderCoupling]]
        self.load: list[Load] = input_data[INVERSE_MODEL_MAPPING_NAME[Load]]
