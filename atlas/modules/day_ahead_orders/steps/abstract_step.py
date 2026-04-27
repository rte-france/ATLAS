"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from pendulum import DateTime

from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters


@dataclass
class StepResult:
    orders: list[OrderDAO] = field(default_factory=list)
    order_couplings: list[OrderCouplingDAO] = field(default_factory=list)


class AbstractOrderStep(ABC):
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
    def formulate(self) -> StepResult:
        """Formulates orders for this step and returns them as a StepResult."""
