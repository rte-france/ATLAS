"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import (
    BusinessModel,
    Hydro,
    Load,
    MarketArea,
    MarketBorder,
    Node,
    OtherNonDispatchable,
    Portfolio,
    Solar,
    Storage,
    Thermal,
    Wind,
)
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.config import INVERSE_MODEL_MAPPING_NAME
from atlas.enum import LoadType
from atlas.models.equipment.equipment import Equipment
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class PortfolioOptimisationInputDataset(AbstractDataset[PortfolioOptimisationParameters]):
    def __init__(
        self,
        input_data: dict[str, list[BusinessModel]],
        parameters: PortfolioOptimisationParameters,
    ):
        self.input_data = input_data
        self.parameters = parameters

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

        self.load: list[Load] = input_data[INVERSE_MODEL_MAPPING_NAME[Load]]

        self.equipments: dict[str, list[type[Equipment]]] = {
            "wind": self.wind,
            "storage": self.storage,
            "hydro": self.hydro,
            "solar": self.solar,
            "thermal": self.thermal,
            "other_non_dispatchable": self.other_non_dispatchable,
            "dispatchable_load": [load for load in self.load if load.load_type == LoadType.POWER_TO_GAS],
            "non_dispatchable_load": [load for load in self.load if load.load_type != LoadType.POWER_TO_GAS],
        }
