"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas import Equipment, Order
from atlas.enums import OrderType, Product
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters


def build_intraday_order(
    equipment: Equipment,
    bid_name: str,
    price: float,
    qmin: float,
    qmax: float,
    order_type: OrderType,
    time: DateTime,
    parameters: IntradayOrdersParameters,
) -> Order:
    return Order(
        name=bid_name,
        market_area=equipment.portfolio.market_area,
        portfolio=equipment.portfolio,
        equipment=equipment,
        qmax=qmax,
        qmin=qmin,
        price=price,
        product=Product.Intraday,
        order_type=order_type,
        is_agent_tso=False,
        execution_date=parameters.temporal.execution_date,
        start_date=time,  # type: ignore[arg-type]
        end_date=time + parameters.temporal.timestep,  # type: ignore[arg-type]
    )
