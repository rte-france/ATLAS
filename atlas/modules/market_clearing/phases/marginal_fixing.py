"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import copy
import json
from collections.abc import Generator

import pendulum

from atlas.enum import OrderType
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.models.order import OrderMC
from atlas.modules.market_clearing.parameters import MarketClearingParameters


class MarginalFixing:
    """
    Module storing the fourth and last step of the Market Clearing process: maximizing the accepted volumes of marginal
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

    def run(self, accepted_powers: dict[tuple[str, str], float], market_prices: dict[tuple[str, int], float]) -> None:
        """

        :param accepted_powers: Result of optimization
        :type accepted_powers: dict[tuple[str, str], float]
        :param market_prices: Result of optimization
        :type market_prices: dict[tuple[str, int], float]
        """
        self.accepted_powers = copy.deepcopy(accepted_powers)
        # Start with looping over time, since all time steps are independent:
        for time_index, time in enumerate(self.input_dataset.times):
            # Loop again immediately on market areas, since they are also,independent of each other:
            for market_area_name in self.input_dataset.mc_market_areas:
                # Get the values of local variables:
                spot_price = market_prices[market_area_name, time_index]
                self.update_accepted_power(market_area_name, time, spot_price)
        if self.parameters.export_lp:
            with open(self.parameters.output_path / "marginal_fixing_accepted_powers.json", "w") as f:
                json.dump([[ma, o, val] for (ma, o), val in self.retrieve_accepted_powers().items()], f)

    def update_accepted_power(self, market_area_name: str, current_time: pendulum.DateTime, spot_price: float) -> None:
        """Update accepted power from clearing

        :param market_area_name: Market area name
        :type market_area_name: str
        :param current_time: Time
        :type current_time: pendulum.Datetime
        :param spot_price: Price of the market area at the current time
        :type spot_price: float
        :return: A generator of OrderMC that may be updated
        :rtype: None
        """
        # Initialize the variables storing the total amounts of usable marginal powers as well as the marginal amounts
        # of balances that can be redistributed:
        max_marginal_sales = 0.0
        max_marginal_purchases = 0.0
        marginal_demand = 0.0
        for mc_order, accepted_power in self.get_marginal_orders(current_time, market_area_name, spot_price):
            if mc_order.order_type == OrderType.Sell:
                max_marginal_sales += mc_order.qmax - mc_order.qmin
                marginal_demand += accepted_power - mc_order.qmin
            else:
                max_marginal_purchases += mc_order.qmax - mc_order.qmin
                marginal_demand -= accepted_power - mc_order.qmin

        sharable_purchase_power = None
        sharable_sale_power = None
        if marginal_demand >= max_marginal_sales - max_marginal_purchases:
            for mc_order, _ in self.get_marginal_orders(current_time, market_area_name, spot_price):
                if mc_order.order_type == OrderType.Sell:
                    self.accepted_powers[market_area_name, mc_order.name] = mc_order.qmax
            sharable_purchase_power = max_marginal_sales - marginal_demand
        else:
            for mc_order, _ in self.get_marginal_orders(current_time, market_area_name, spot_price):
                if mc_order.order_type == OrderType.Buy:
                    self.accepted_powers[market_area_name, mc_order.name] = mc_order.qmax
            sharable_sale_power = max_marginal_purchases + marginal_demand

        if sharable_purchase_power is not None:
            for mc_order, _ in self.get_marginal_orders(current_time, market_area_name, spot_price):
                if (
                    mc_order.order_type == OrderType.Buy
                    and max_marginal_purchases * (mc_order.qmax - mc_order.qmin) != 0
                ):
                    self.accepted_powers[market_area_name, mc_order.name] = (
                        mc_order.qmin
                        + sharable_purchase_power / max_marginal_purchases * (mc_order.qmax - mc_order.qmin)
                    )
        else:
            for mc_order, _ in self.get_marginal_orders(current_time, market_area_name, spot_price):
                if mc_order.order_type == OrderType.Sell and max_marginal_sales * (mc_order.qmax - mc_order.qmin) != 0:
                    self.accepted_powers[market_area_name, mc_order.name] = (
                        mc_order.qmin + sharable_sale_power / max_marginal_sales * (mc_order.qmax - mc_order.qmin)
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
        for mc_order in self.input_dataset.mc_orders.values():
            if mc_order.market_area.name != market_area_name:
                continue
            if not mc_order.start_date <= current_time < mc_order.end_date_processed:
                continue
            if (mc_order.end_datetime - mc_order.start_date).total_seconds() > self.parameters.timestep.total_seconds():
                continue
            if mc_order.price != spot_price:
                continue
            if mc_order.is_linked or mc_order.id_with_status:
                continue

            accepted_power = self.accepted_powers[market_area_name, mc_order.name]
            if mc_order.qmin == 0.0 or (mc_order.qmax != mc_order.qmin and accepted_power != 0.0):
                yield mc_order, accepted_power

    def retrieve_accepted_powers(self) -> dict[tuple[str, str], float]:
        """Retrieve tje accepted powers of each order per area

        :rtype: dict[tuple[str, str], float]
        """
        return self.accepted_powers
