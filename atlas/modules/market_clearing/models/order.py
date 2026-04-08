"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
from pendulum import Duration
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.enums import OrderType, Product
from atlas.log import logger
from atlas.models.market.market_area import MarketArea
from atlas.models.market.order import Order
from atlas.modules.market_clearing.parameters import MarketClearingParameters


class OrderMC(Order):
    # Override of parent class  attributes that were None
    market_area: MarketArea
    execution_date: DateTime
    start_date: DateTime
    end_date: DateTime
    product: Product
    order_type: OrderType
    qmax: float
    qmin: float

    # Attributes that will be set later (while creating coupling groups):
    id_with_status: bool = False
    is_mutually_excluding: bool = False
    is_linked: bool = False
    link_id: str | None = None
    group_index: int | None = None
    time_index: int | None = None
    is_parent_children: bool = False
    parent_child_id: str | None = None
    full_link_id: int | None = None
    full_pc_id: int | None = None
    child_id: str | None = None
    is_parent: bool = False
    order_coupling_parent_ids: list[str] | None = None
    circular_pc_id: int | None = None

    # Attributes from market clearing parameter
    timestep: Duration

    @property
    def production_sign(self) -> int:
        return 1 if self.order_type == OrderType.Sell else -1

    @property
    def is_sale(self) -> bool:
        return self.production_sign == 1

    # Deduce duration from list of DataTime and the parameter time step (the end datetime may have to be modified so that
    # everything stays consistent).
    # NB: by convention, self.end_date are actually starts of a last time step:
    @property
    def duration(self) -> pendulum.Duration:
        minutes = (
            self.end_date.diff(self.start_date).in_minutes()
            // self.timestep.total_minutes()
            * self.timestep.total_minutes()
        )
        return pendulum.duration(minutes=minutes)

    @property
    def end_datetime(self) -> DateTime:
        return self.start_date + self.duration

    @property
    def end_date_processed(self) -> DateTime:
        return self.start_date + self.duration

    @staticmethod
    def is_feasible(order: Order, times: list[pendulum.DateTime], parameters: MarketClearingParameters) -> bool:
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
        if order.end_date > parameters.temporal.end_date:
            return False

        # For overlapping markets, such as (Intraday or Balancing), we need to only
        # consider orders that have an ExecutionDate close to the Clearing execution_date
        # The concept of "close" is here defined by the execution_date_tolerance parameter
        tolerance = parameters.execution_datetime_tolerance
        if (parameters.temporal.execution_date - order.execution_date).total_seconds() / 60 > float(tolerance):
            return False

        # MS
        duration_span = order.end_date.diff(order.start_date).as_duration()
        if parameters.temporal.timestep > duration_span:
            logger.info(
                f"Order {order.name} is not considered because not long enough. Duration {duration_span} min while clearing is timestep {parameters.temporal.timestep} min"
            )
            return False

        if order.market_area is None:
            logger.info(f"Order {order.name} is not considered because there is no market area")
            return False

        # Check if order is in a market area considered
        if (
            isinstance(parameters.market_area_names, list)
            and order.market_area.name not in parameters.market_area_names
        ):
            logger.info(
                f"Order {order.name} is not considered because not in market area considered : {parameters.market_area_names}"
            )
            return False

        return True

    # Useful for pricing only
    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        if isinstance(other, Order) and other.name == self.name:
            return True
        return False

    ##########################
