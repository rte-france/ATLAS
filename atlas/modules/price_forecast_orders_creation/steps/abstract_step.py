"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from pendulum import DateTime

from atlas import Equipment
from atlas.enums import OrderType
from atlas.modules.price_forecast_orders_creation.input_objects.order import OrderPFOC
from atlas.modules.price_forecast_orders_creation.input_objects.order_coupling import OrderCouplingPFOC
from atlas.modules.price_forecast_orders_creation.parameters import PriceForecastOrdersCreationParameters
from atlas.modules.price_forecast_orders_creation.result import PriceForecastOrdersCreationResult


@dataclass
class StepResult:
    orders: list[OrderPFOC] = field(default_factory=list)
    order_couplings: list[OrderCouplingPFOC] = field(default_factory=list)


class AbstractOrderStep(ABC):
    def __init__(
        self,
        dataset: PriceForecastOrdersCreationResult,
        orders_time: list[DateTime],
        parameters: PriceForecastOrdersCreationParameters,
    ) -> None:
        self.dataset = dataset
        self.orders_time = orders_time
        self.parameters = parameters

    @abstractmethod
    def formulate(self) -> StepResult:
        """Formulates orders for this step and returns them as a StepResult."""

    def create_order(
        self,
        time: DateTime,
        equipment: Equipment,
        order_type: OrderType,
        price: float,
        qmin: float,
        qmax: float,
        is_agent_tso: bool,
        suffix_name: str = "",
    ) -> OrderPFOC | None:
        if order_type == OrderType.Buy:
            qmax = math.floor(qmax)
            qmin = math.floor(qmin)
        else:
            if qmin != 0:
                qmax_diff = math.ceil(qmax) - float(qmax)
                qmax = math.ceil(qmax)
                qmin = qmin + qmax_diff
            else:
                qmax = math.ceil(qmax)

        # Do not formulate the order if qmax == 0
        if qmax <= 0:
            return None

        price = min(self.parameters.market_price_cap, round(price, 2))
        price = max(-self.parameters.market_price_cap, price)

        name = equipment.Name + "_" + self.parameters.market + "_" + {time.format("DD_MM_YYYY_HH_mm_ss")} + suffix_name
        return OrderPFOC(
            name=name,
            market_area=equipment.portfolio.market_area,
            portfolio=equipment.portfolio,
            equipment=equipment,
            qmax=qmax,
            qmin=qmin,
            price=price,
            product=self.parameters.market,
            order_type=order_type,
            is_agent_tso=is_agent_tso,
        )
