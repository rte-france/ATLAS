"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractOrderFormulator.
"""

from abc import ABC, abstractmethod

import pandas as pd
from pendulum import DateTime

from atlas.enums import MarketType, OrderType, Product
from atlas.modules.balancing_market_bsp_orders.parameters import BSPBalancingOrdersParameters
from atlas.objects.market.order import Order


class AbstractOrderFormulator(ABC):
    """Abstract base class for balancing order formulators.

    Provides shared logic for:
    - Computing procured power timeseries (FCR, aFRR, mFRR/RR depending on product type)
    - Computing available upward and downward power
    - Filtering timesteps by setup delay
    - Building Order instances

    Subclasses implement formulate() and override max/min power extraction
    where the equipment type differs (e.g. Load uses maximum_power_forecast).
    """

    def __init__(
        self,
        equipment,  # TODO : typing
        time_index: list[DateTime],
        parameters: BSPBalancingOrdersParameters,
    ) -> None:
        self.equipment = equipment
        self.time_index = time_index
        self.parameters = parameters

    @abstractmethod
    def formulate(self) -> tuple[list[Order], list]:
        """
        Formulate upward and downward orders for the equipment.

        :return: Tuple of formulated Order instances and OrderCoupling instances
        :rtype: tuple[list[Order], list]
        """

    def compute_procured_power(
        self,
        execution_date: DateTime,
        start: DateTime,
        end: DateTime,
        product_type: MarketType,
    ) -> tuple[pd.Series, pd.Series]:
        """
        Compute total upward and downward procured power across all reserve types.

        FCR and aFRR are always included. mFRR or RR is added depending on product_type
        to avoid double-counting with the market being formulated.

        :param execution_date: Execution date for forecast extraction
        :type execution_date: DateTime
        :param start: Start of the balancing time frame
        :type start: DateTime
        :param end: End of the balancing time frame
        :type end: DateTime
        :param product_type: Type of market (RR, mFRR)
        :type product_type: MarketType
        :return: Tuple of (upward_procured, downward_procured)
        :rtype: tuple[pd.Series, pd.Series]
        """

        upward = self.equipment.fcr_up_procured.get_forecast(
            execution_date, start, end
        ) + self.equipment.afrr_up_procured.get_forecast(execution_date, start, end)
        downward = self.equipment.fcr_down_procured.get_forecast(
            execution_date, start, end
        ) + self.equipment.afrr_down_procured.get_forecast(execution_date, start, end)

        if product_type == MarketType.rr_activation:
            upward = upward + self.equipment.mfrr_up_procured.get_forecast(execution_date, start, end)
            downward = downward + self.equipment.mfrr_down_procured.get_forecast(execution_date, start, end)
        elif product_type == MarketType.mfrr_activation:
            upward = upward + self.equipment.rr_up_procured.get_forecast(execution_date, start, end)
            downward = downward + self.equipment.rr_down_procured.get_forecast(execution_date, start, end)

        return upward, downward

    def is_after_setup_delay(self, time: DateTime) -> bool:
        """
        Return True if enough time has passed since execution_date for the equipment to react.

        :param time: The timestep being evaluated
        :type time: DateTime
        :return: Whether the setup delay has elapsed
        :rtype: bool
        """
        elapsed_minutes = (time - self.parameters.temporal.execution_date).total_seconds() / 60
        return elapsed_minutes >= self.equipment.setup_delay * 60

    def build_order(
        self,
        order_type: OrderType,
        start: DateTime,
        end: DateTime,
        price: float,
        qmin: float,
        qmax: float,
    ) -> Order | None:
        """
        Build an Order instance from the given parameters.

        Applies price cap and rounding. Returns None if qmax rounds to 0.

        :param order_type: Buy or Sell
        :type order_type: OrderType
        :param start: Order start datetime
        :type start: DateTime
        :param end: Order end datetime
        :type end: DateTime
        :param price: Raw order price in euro/MWh
        :type price: float
        :param qmin: Minimum accepted quantity in MW
        :type qmin: float
        :param qmax: Maximum accepted quantity in MW
        :type qmax: float
        :return: Formulated Order instance, or None if qmax rounds to 0
        :rtype: Order | None
        """
        qmax = round(qmax)
        if qmax == 0:
            return None
        qmin = round(qmin)

        price = min(self.parameters.market_price_cap, round(price, 2))
        price = max(-self.parameters.market_price_cap, price)

        return Order(
            name=self._build_order_name(order_type, start, end),
            execution_date=self.parameters.temporal.execution_date,
            start_date=start,
            end_date=end,
            product=Product(self.parameters.product_type.value),
            order_type=order_type,
            price=price,
            qmin=qmin,
            qmax=qmax,
            is_agent_tso=False,
            equipment=self.equipment,
            portfolio=self.equipment.portfolio,
            market_area=self.equipment.portfolio.market_area,
        )

    def _build_order_name(self, order_type: OrderType, start: DateTime, end: DateTime) -> str:
        """
        Build a standardised order name.

        Format: {equipment}_{market}_{direction}_{start_hhmm}_{end_hhmm}_at_{execution_hhmm}

        :param order_type: Buy or Sell
        :type order_type: OrderType
        :param start: Order start datetime
        :type start: DateTime
        :param end: Order end datetime
        :type end: DateTime
        :return: Standardised order name
        :rtype: str
        """
        direction = "U" if order_type == OrderType.sell else "D"
        market_short = self._market_short_name()
        return (
            f"{self.equipment.name}_{market_short}_{direction}_"
            f"{self._fmt_time(start)}_{self._fmt_time(end)}_"
            f"at_{self._fmt_time(self.parameters.temporal.execution_date)}"
        )

    def _market_short_name(self) -> str:
        """
        Return a short market name string for use in order names.

        :return: Short market name ('RR', 'MFRR', or 'Other')
        :rtype: str
        """
        if self.parameters.product_type == MarketType.rr_activation:
            return "RR"
        if self.parameters.product_type == MarketType.mfrr_activation:
            return "MFRR"
        return "Other"

    @staticmethod
    def _fmt_time(dt: DateTime) -> str:
        """
        Format a DateTime to HH_MM string for use in order names.

        :param dt: Datetime to format
        :type dt: DateTime
        :return: Formatted time string
        :rtype: str
        """
        return dt.strftime("%H_%M")
