"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractOrderFormulator.
"""

from abc import ABC, abstractmethod

from pendulum import DateTime

from atlas.enums import MarketType, OrderType, Product
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.timeseries import Timeseries
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
        target_times: list[DateTime],
        parameters: BSPBalancingOrdersParameters,
    ) -> None:
        self.equipment = equipment
        self.target_times = target_times
        self.parameters = parameters

    @abstractmethod
    def formulate(self) -> tuple[list[Order], list]:
        """
        Formulate upward and downward orders for the equipment.

        :return: Tuple of formulated Order instances and OrderCoupling instances
        :rtype: tuple[list[Order], list]
        """

    def _get_forecast_or_zero(
        self,
        matrix: ForecastingMatrix | LazyForecastingMatrix | None,
        execution_date: DateTime,
        start: DateTime,
        end: DateTime,
    ) -> Timeseries:
        """
        Extract a forecast from a ForecastingMatrix, or return a zero Timeseries if None.

        :param matrix: ForecastingMatrix to extract from, or None
        :type matrix: ForecastingMatrix | LazyForecastingMatrix | None
        :param execution_date: Execution date for forecast extraction
        :type execution_date: DateTime
        :param start: Start of the time frame
        :type start: DateTime
        :param end: End of the time frame
        :type end: DateTime
        :return: Extracted Timeseries, or a zero-valued Timeseries over [start, end]
        :rtype: Timeseries
        """
        if matrix is None:
            return Timeseries.from_index(start, self.parameters.temporal.timestep, end, default_value=0.0)
        return matrix.get_forecast(execution_date, start, end)

    def compute_procured_power(
        self,
        execution_date: DateTime,
        start: DateTime,
        end: DateTime,
        product_type: MarketType,
    ) -> tuple[Timeseries, Timeseries]:
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
        :rtype: tuple[Timeseries, Timeseries]
        """

        upward = self._get_forecast_or_zero(
            self.equipment.fcr_up_procured, execution_date, start, end
        ) + self._get_forecast_or_zero(self.equipment.afrr_up_procured, execution_date, start, end)
        downward = self._get_forecast_or_zero(
            self.equipment.fcr_down_procured, execution_date, start, end
        ) + self._get_forecast_or_zero(self.equipment.afrr_down_procured, execution_date, start, end)

        if product_type == MarketType.rr_activation:
            upward = upward + self._get_forecast_or_zero(self.equipment.mfrr_up_procured, execution_date, start, end)
            downward = downward + self._get_forecast_or_zero(
                self.equipment.mfrr_down_procured, execution_date, start, end
            )
        elif product_type == MarketType.mfrr_activation:
            upward = upward + self._get_forecast_or_zero(self.equipment.rr_up_procured, execution_date, start, end)
            downward = downward + self._get_forecast_or_zero(
                self.equipment.rr_down_procured, execution_date, start, end
            )

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
        suffix: str = "",
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
        :param suffix: Optional suffix appended to the order name (e.g. '_selfbal')
        :type suffix: str
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
            name=self._build_order_name(order_type, start, end, suffix),
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

    def _build_order_name(
        self,
        order_type: OrderType,
        start: DateTime,
        end: DateTime,
        suffix: str = "",
    ) -> str:
        """
        Build a standardised order name.

        Format: {equipment}_{market}_{direction}_{start_hhmm}_{end_hhmm}_at_{execution_hhmm}{suffix}

        :param order_type: Buy or Sell
        :type order_type: OrderType
        :param start: Order start datetime
        :type start: DateTime
        :param end: Order end datetime
        :type end: DateTime
        :param suffix: Optional suffix appended to the order name (e.g. '_selfbal')
        :type suffix: str
        :return: Standardised order name
        :rtype: str
        """
        direction = "U" if order_type == OrderType.Sell else "D"
        market_short = self._market_short_name()
        return (
            f"{self.equipment.name}_{market_short}_{direction}_"
            f"{self._fmt_time(start)}_{self._fmt_time(end)}_"
            f"at_{self._fmt_time(self.parameters.temporal.execution_date)}{suffix}"
        ).lower()

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

    def _apply_gradient_constraint(
        self,
        forecasted_power,
        time: DateTime,
        upward_available: float,
        downward_available: float,
    ) -> tuple[float, float]:
        """
        Apply the maximum_gradient constraint to the available upward and downward power at a given timestep.

        Limits the available power based on the forecasted power evolution between the
        studied timestep and its previous/next neighbor, so that the equipment's power
        trajectory never exceeds maximum_gradient per timestep.

        :param forecasted_power: Forecasted power timeseries over the balancing time frame
        :type forecasted_power: Timeseries
        :param time: The timestep being evaluated
        :type time: DateTime
        :param upward_available: Upward available power before the gradient constraint
        :type upward_available: float
        :param downward_available: Downward available power before the gradient constraint
        :type downward_available: float
        :return: Tuple of (upward_available, downward_available) after the gradient constraint
        :rtype: tuple[float, float]
        """
        timestep = self.parameters.temporal.timestep
        execution_date = self.parameters.temporal.execution_date
        max_grad = self.equipment.maximum_gradient * (timestep.total_seconds() / 60)

        previous_time = time.subtract(minutes=int(timestep.total_seconds() // 60))
        next_time = time.add(minutes=int(timestep.total_seconds() // 60))

        try:
            previous_forecasted_power = self.equipment.power.get_forecast(
                execution_date, previous_time, previous_time
            ).get_value(previous_time)
            if previous_forecasted_power is None:
                previous_forecasted_power = 0.0
        except (KeyError, ValueError):
            previous_forecasted_power = 0.0

        try:
            next_forecasted_power = self.equipment.power.get_forecast(execution_date, next_time, next_time).get_value(
                next_time
            )
            if next_forecasted_power is None:
                next_forecasted_power = 0.0
        except (KeyError, ValueError):
            next_forecasted_power = 0.0

        if previous_forecasted_power > 0:
            previous_upward_evolution = max(forecasted_power.get_value(time) - previous_forecasted_power, 0)
            previous_downward_evolution = max(previous_forecasted_power - forecasted_power.get_value(time), 0)
        else:
            previous_upward_evolution = 0.0
            previous_downward_evolution = 0.0

        if next_forecasted_power > 0:
            next_upward_evolution = max(next_forecasted_power - forecasted_power.get_value(time), 0)
            next_downward_evolution = max(forecasted_power.get_value(time) - next_forecasted_power, 0)
        else:
            next_upward_evolution = 0.0
            next_downward_evolution = 0.0

        upward_available = min(
            upward_available,
            max_grad - previous_upward_evolution,
            max_grad - next_downward_evolution,
        )
        downward_available = min(
            downward_available,
            max_grad - previous_downward_evolution,
            max_grad - next_upward_evolution,
        )

        return max(0.0, upward_available), max(0.0, downward_available)
