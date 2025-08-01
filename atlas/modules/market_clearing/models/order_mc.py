"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from pendulum import Duration
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.enum import OrderType, Product
from atlas.logging import logger
from atlas.models.market.order import Order
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters


class OrderMC(Order):
    # Override of parent class  attributes that were None
    accepted_power: float
    execution_date: DateTime
    start_date: DateTime
    end_date: DateTime
    product: Product
    order_type: OrderType
    qmax: float
    qmin: float

    # Attributes that will be set later (while creating coupling groups):
    id_with_status: int | None = None
    is_mutually_excluding: bool = False
    is_linked: bool = False
    link_id: str | None = None
    group_index: int | None = None
    is_parent_children: bool = False
    parent_child_id: str | None = None
    full_link_id: int | None = None
    full_pc_id: int | None = None
    child_id: str | None = None
    is_parent: bool = False
    parent_id: bool = False
    circular_pc_id: int | None = None

    # Attributes from market clearing parameter
    time_step: Duration

    @property
    def production_sign(self) -> int:
        return 1 if self.order_type == OrderType.Sell else -1

    @property
    def is_sale(self) -> bool:
        return True if self.production_sign == 1 else False

    # Deduce duration from list of DataTime and the parameter time step (the end datetime may have to be modified so that
    # everything stays consistent).
    # NB: by convention, self.end_date are actually starts of a last time step:
    @property
    def duration(self) -> int:
        return int(
            (((self.end_date - self.start_date).total_seconds() / 60) //
             int(self.time_step.total_minutes())) * 60
        )

    @property
    def end_datetime(self) -> DateTime:
        return self.start_date.add(minutes=self.duration)

    @property
    def end_date_processed(self) -> DateTime:
        return self.start_date.add(minutes=self.duration)

    @staticmethod
    def is_feasible(order: Order, times: list[DateTime], parameters: MarketClearingParameters) -> bool:
        """Check if an order from the marker is feasible or not.

        The first attributes to check are dates: they must lie in the time window of the simulation, as defined in the
        parameters.

        :param order: Order to check
        :type order: Order
        :param times: DateTimes used in optimization
        :type times: list[DateTime]
        :param parameters: Parameters of Market Clearing
        :type parameters: MarketClearingParameters
        :return: True if the order is feasible otherwise False
        :rtype: Bool
        """
        # check None value
        if order.product is None or order.start_date is None or order.end_date is None or order.execution_date is None:
            return False
        # Take order depending on the considered market:
        if not parameters.market == order.product:
            return False

        # Check that the start datetime complies with the discretized time
        # interval of the simulation:
        if order.start_date not in times:
            return False

        # Check that the end datetime also does, but to within 1 minute:
        if order.end_date > parameters.end_date:
            return False

        # For overlapping markets, such as (Intraday or Balancing), we need to only
        # consider orders that have an ExecutionDate close to the Clearing execution_date
        # The concept of "close" is here defined by the execution_date_tolerance parameter
        tolerance = parameters.execution_datetime_tolerance
        if (parameters.execution_date - order.execution_date).total_seconds() / 60 > float(tolerance):
            return False

        # MS
        duration_span = Duration(seconds=(order.end_date - order.start_date).total_seconds())
        if parameters.time_step > duration_span:
            logger.info(
                f"Order {order.name} is not considered because not long enough. Duration {duration_span} min while clearing is timestep {parameters.time_step} min"
            )
            return False

        return True