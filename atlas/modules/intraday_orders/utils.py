"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas.enums import OrderType, Product
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.objects.equipment.equipment import Equipment
from atlas.objects.market.order import Order
from atlas.timing import generate_datetimes


def engaged_quantity(equipment: Equipment, parameters: IntradayOrdersParameters) -> AbstractTimeseries:
    """Cumulative cleared engagement over the order window: day-ahead plus all prior intraday clearings.

    ``total_id_cleared_quantity`` is ``None`` until the first intraday clearing has run, in
    which case it counts as zero. Timestamps in the order window with no DA clearing data
    (e.g. a thermal unit not committed in DA for the next day) are treated as zero engagement.

    :param equipment: Equipment whose cleared engagement is computed.
    :type equipment: Equipment
    :param parameters: Intraday orders parameters defining the order window.
    :type parameters: IntradayOrdersParameters
    :raises ValueError: If the equipment has no day-ahead cleared quantity.
    :return: The summed engagement timeseries over the order window, zero-filled where no DA data exists.
    :rtype: AbstractTimeseries
    """
    da = equipment.da_cleared_quantity
    if da is None:
        raise ValueError(f"{equipment.name} has no day-ahead cleared quantity")
    total_id = equipment.total_id_cleared_quantity
    engagement = da if total_id is None else da + total_id
    # Zero baseline for the full order window; add engagement where it overlaps.
    # ponytail: from_index + filtered-subset avoids get_value on empty timeseries when DA data
    # doesn't cover the order window (e.g. thermal peak not committed in DA for the next day).
    baseline = Timeseries.from_index(
        parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, 0.0
    )
    order_window = generate_datetimes(
        parameters.temporal.start_date, parameters.penultimate_date, parameters.temporal.timestep
    )
    filtered = engagement.filter(order_window, inplace=False)
    return baseline if len(filtered) == 0 else baseline + filtered


def build_intraday_order(
    equipment: Equipment,
    bid_name: str,
    price: float,
    qmin: float,
    qmax: float,
    order_type: OrderType,
    time: DateTime,
    parameters: IntradayOrdersParameters,
    is_agent_tso: bool | None = False,
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
        is_agent_tso=is_agent_tso,
        execution_date=parameters.temporal.execution_date,
        start_date=time,  # type: ignore[arg-type]
        end_date=time + parameters.temporal.timestep,  # type: ignore[arg-type]
    )
