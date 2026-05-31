"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from abc import ABC, abstractmethod

from pendulum import DateTime

from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.result import BiddingResult


class AbstractBiddingStep(ABC):
    def __init__(
        self,
        dataset: DayAheadOrdersOutput,
        orders_time: list[DateTime],
        parameters: DayAheadOrdersParameters,
    ) -> None:
        self.dataset = dataset
        self.orders_time = orders_time
        self.parameters = parameters

    @abstractmethod
    def formulate(self) -> BiddingResult:
        """Formulates orders for this step and returns them as a BiddingResult."""
