"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic_extra_types.pendulum_dt import DateTime

from atlas.logging import logger

from atlas.models.market.order import Order
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters


class MCOrder:
    instance_with_status_count = 0

    @staticmethod
    def generate_instance_with_status_id():
        instance_id = MCOrder.instance_with_status_count
        MCOrder.instance_with_status_count += 1
        return instance_id

    def __init__(self, order: Order):
        self.order = order
        # Deduce duration from list of DataTime and the parameter time step (the end datetime may have to be modified so that
        # everything stays consistent).
        # NB: by convention, self.end_date are actually starts of a last time step:
        self.duration = (((self.end_date - self.start_date).total_seconds() / 60) // self.parameters.time_step) * 60
        self.end_date_processed = self.start_date.add(minutes=self.duration)

        # Attributes that will be set later (while creating coupling groups):
        self.id_with_status = None
        self.is_mutually_excluding = False
        self.is_linked = False
        self.link_id = None
        self.group_index = None
        self.is_parent_children = False
        self.parent_child_id = None
        self.full_link_id = None
        self.full_pc_id = None
        self.child_id = None
        self.is_parent = False
        self.parent_id = False
        self.circular_pc_id = None

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
        if (parameters.execution_datetime - order.execution_date).total_seconds() / 60 > float(tolerance):
            return False

        # MS
        duration_span = (order.end_date - order.start_date).total_seconds() / 60
        if parameters.time_step > duration_span:
            logger.info(
                f"Order {order.name} is not considered because not long enough. Duration {duration_span} min while clearing is timestep {parameters.time_step} min"
            )
            return False

        return True

