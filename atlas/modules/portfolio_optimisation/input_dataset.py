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
from atlas.timing import generate_datetimes


class PortfolioOptimisationInputDataset(AbstractDataset[PortfolioOptimisationParameters]):
    def __init__(
        self,
        input_data: dict[str, list[BusinessModel]],
        parameters: PortfolioOptimisationParameters,
    ):
        self.input_data = input_data
        self.parameters = parameters

        self.times = generate_datetimes(
            start=self.parameters.start_date,
            end=self.parameters.end_date,
            freq=self.parameters.time_step,
        )

        self.control_block = input_data[INVERSE_MODEL_MAPPING_NAME[ControlBlock]]
        self.market_area = input_data[INVERSE_MODEL_MAPPING_NAME[MarketArea]]
        self.market_border = input_data[INVERSE_MODEL_MAPPING_NAME[MarketBorder]]
        self.node = input_data[INVERSE_MODEL_MAPPING_NAME[Node]]
        self.portfolio = input_data[INVERSE_MODEL_MAPPING_NAME[Portfolio]]
        self.wind = input_data[INVERSE_MODEL_MAPPING_NAME[Wind]]
        self.storage = input_data[INVERSE_MODEL_MAPPING_NAME[Storage]]
        self.hydro = input_data[INVERSE_MODEL_MAPPING_NAME[Hydro]]
        self.solar = input_data[INVERSE_MODEL_MAPPING_NAME[Solar]]
        self.thermal = input_data[INVERSE_MODEL_MAPPING_NAME[Thermal]]
        self.other_non_dispatchable = input_data[INVERSE_MODEL_MAPPING_NAME[OtherNonDispatchable]]
        self.order = input_data[INVERSE_MODEL_MAPPING_NAME[Order]]
        self.order_coupling = input_data[INVERSE_MODEL_MAPPING_NAME[OrderCoupling]]
        self.load = input_data[INVERSE_MODEL_MAPPING_NAME[Load]]

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
