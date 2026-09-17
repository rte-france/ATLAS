"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import copy
import json
from collections.abc import Generator

import pendulum

from atlas.enums import OrderType
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.parameters import MarketClearingParameters


class MarginalFixing:
    """
    Phase storing the fourth and last step of the Market Clearing process: maximizing the accepted volumes of marginal
    orders.

    The previous steps have determined which orders could be associated with each others in order to maximize the
    social welfare, which exchanges it induced at borders and what were the resulting market prices. However, some
    orders which price is equal to the market price might remain unaccepted, whereas their price is equal to the market
    price. Indeed, their acceptance would not modify the overall social welfare. The present step is dedicated to
    finding such orders, called "marginal", and maximizing the volumes they can trade.
    """

    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.accepted_powers: dict[tuple[str, str], float] = {}

    def compute(
        self, accepted_powers: dict[tuple[str, str], float], market_prices: dict[tuple[str, pendulum.DateTime], float]
    ) -> None:
        """

        :param accepted_powers: Result of optimization
        :type accepted_powers: dict[tuple[str, str], float]
        :param market_prices: Result of optimization
        :type market_prices: dict[tuple[str, pendulum.DateTime], float]
        """
        self.accepted_powers = copy.deepcopy(accepted_powers)
        # Start with looping over time, since all time steps are independent:
        for time in self.input_dataset.times:
            # Loop again immediately on market areas, since they are also,independent of each other:
            for market_area_name in self.input_dataset.market_areas:
                # Get the values of local variables:
                spot_price = market_prices[market_area_name, time]
                self.update_accepted_power(market_area_name, time, spot_price)
        if self.parameters.solver.export_lp:
            with open(
                self.parameters.get_lp_dir() / "marginal_fixing_accepted_powers.json",
                "w",
            ) as f:
                json.dump([[ma, o, val] for (ma, o), val in self.get_accepted_powers().items()], f)

    def update_accepted_power(self, market_area_name: str, current_time: pendulum.DateTime, spot_price: float) -> None:
        """Update accepted power from clearing

        :param market_area_name: Market area name
        :type market_area_name: str
        :param current_time: Time
        :type current_time: pendulum.Datetime
        :param spot_price: Price of the market area at the current time
        :type spot_price: float
        :rtype: None
        """
        # Initialize the variables storing the total amounts of usable marginal powers as well as the marginal amounts
        # of balances that can be redistributed:
        marginal_orders = list(self.get_marginal_orders(current_time, market_area_name, spot_price))

        max_marginal_sales = 0.0
        max_marginal_purchases = 0.0
        marginal_demand = 0.0
        for order, accepted_power in marginal_orders:
            if order.order_type == OrderType.Sell:
                max_marginal_sales += order.qmax - order.qmin
                marginal_demand += accepted_power - order.qmin
            else:
                max_marginal_purchases += order.qmax - order.qmin
                marginal_demand -= accepted_power - order.qmin

        sharable_purchase_power = None
        sharable_sale_power = None
        if marginal_demand >= max_marginal_sales - max_marginal_purchases:
            for order, _ in marginal_orders:
                if order.order_type == OrderType.Sell:
                    self.accepted_powers[market_area_name, order.name] = order.qmax
            sharable_purchase_power = max_marginal_sales - marginal_demand
        else:
            for order, _ in marginal_orders:
                if order.order_type == OrderType.Buy:
                    self.accepted_powers[market_area_name, order.name] = order.qmax
            sharable_sale_power = max_marginal_purchases + marginal_demand

        if sharable_purchase_power is not None:
            for order, _ in marginal_orders:
                if order.order_type == OrderType.Buy and max_marginal_purchases * (order.qmax - order.qmin) != 0:
                    self.accepted_powers[market_area_name, order.name] = (
                        order.qmin + sharable_purchase_power / max_marginal_purchases * (order.qmax - order.qmin)
                    )
        else:
            for order, _ in marginal_orders:
                if order.order_type == OrderType.Sell and max_marginal_sales * (order.qmax - order.qmin) != 0:
                    self.accepted_powers[market_area_name, order.name] = (
                        order.qmin + sharable_sale_power / max_marginal_sales * (order.qmax - order.qmin)
                    )

    def get_marginal_orders(
        self, current_time: pendulum.DateTime, market_area_name: str, spot_price: float
    ) -> Generator[tuple[OrderMC, float]]:
        """Generator selecting marginal orders that can be involved in the redistribution process

        :param current_time: Time
        :type current_time: pendulum.Datetime
        :param market_area_name: Market area name
        :type market_area_name: str
        :param spot_price: Price of the market area at the current time
        :type spot_price: float
        :return: A generator of OrderMC that may be updated
        :rtype: list[OrderMC]
        """
        for order in self.input_dataset.orders.values():
            if order.market_area.name != market_area_name:
                continue
            if not order.start_date <= current_time < order.end_date_processed:
                continue
            if (
                order.end_date_processed - order.start_date
            ).total_seconds() > self.parameters.temporal.timestep.total_seconds():
                continue
            if order.price != spot_price:
                continue
            if order.is_linked or order.requires_status_variable:
                continue

            accepted_power = self.accepted_powers[market_area_name, order.name]
            if order.qmin == 0.0 or (order.qmax != order.qmin and accepted_power != 0.0):
                yield order, accepted_power

    def get_accepted_powers(self) -> dict[tuple[str, str], float]:
        """Retrieve the accepted powers of each order per area

        :rtype: dict[tuple[str, str], float]
        """
        return self.accepted_powers
