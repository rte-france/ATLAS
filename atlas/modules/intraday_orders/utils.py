"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import List, Callable, Type

from pendulum import DateTime
from pydantic_extra_types.pendulum_dt import Duration

import atlas.config as cfg
from atlas import Equipment
from atlas.enums import OrderType, Product
from atlas.modules.intraday_orders.models.order import IntraDayOrder
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters


def get_orders_timestamps(start_date: DateTime, end_date: DateTime, time_step: Duration) -> List[DateTime]:
    orders_timestamps = [start_date]
    while orders_timestamps[-1] + time_step <= end_date:
        orders_timestamps.append(orders_timestamps[-1] + time_step)
    return orders_timestamps


def get_date_to_clean_string(date: DateTime):
    """
    Converts a datetime object to a string without special characters
    """
    string = str(date)
    string = string.replace("/", "_").replace(":", "_").replace(" ", "_")
    return string


def build_intraday_order(
    equipment: Equipment,
    bid_name: str,
    price: float,
    qmin: float,
    qmax: float,
    order_type: OrderType,
    time: DateTime,
    parameters: IntradayOrdersParameters,
) -> IntraDayOrder:
    return IntraDayOrder(
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
        execution_date=parameters.execution_date,
        start_date=time,
        end_date=time + parameters.timestep,
    )


def intraday_step(step_name: str):
    """
    Decorator method to wrap an intraday formulation step with log messages.
    """
    message = f"Formulation of the intraday {step_name} orders"

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            cfg.logger.info(f"{message} [start]")
            result = func(*args, **kwargs)
            cfg.logger.info(f"{message} [end]")
            return result

        return wrapper

    return decorator
