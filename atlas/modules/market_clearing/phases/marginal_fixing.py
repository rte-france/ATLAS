"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from atlas import MarketArea
from atlas.enum import OrderType
from atlas.modules.market_clearing.market_clearing_data.market_clearing_order import MCOrder
from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters


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

    def run(self, accepted_powers: dict[str, dict[str, float]], market_prices: dict[str, list[float]]):
        """

        :param accepted_powers: Result of optimization
        :type accepted_powers: dict[str, dict[str, float]]
        :param market_prices: Result of optimization
        :type market_prices: dict[str, list[float]]
        """
        # Start with looping over time, since all time steps are independent:
        for time_index, time in enumerate(self.input_dataset.times):
            # Loop again immediately on market areas, since they are also,independent of each other:
            for area in self.input_dataset.mc_market_areas:
                # Get the values of local variables:
                spot_price = market_prices[area.market_area.name][time_index]
                local_accepted_powers = accepted_powers[area.market_area.name]
                self.update_local_accepted_power(local_accepted_powers, area, time, spot_price)

    def update_local_accepted_power(self, local_accepted_powers: dict[str, float], area: MarketArea, time, spot_price: float):
        # Initialize the variables storing the total amounts of usable marginal powers as well as the marginal amounts
        # of balances that can be redistributed:
        max_marginal_sales = 0.0
        max_marginal_purchases = 0.0
        marginal_demand = 0.0
        for order, accepted_power in self.get_marginal_orders(time, area, spot_price, local_accepted_powers):
            if order.order_type == OrderType.Sell:
                max_marginal_sales += order.q_max - order.q_min
                marginal_demand += accepted_power - order.q_min
            else:
                max_marginal_purchases += order.q_max - order.q_min
                marginal_demand -= accepted_power - order.q_min

            sharable_purchase_power = None
            sharable_sale_power = None
            if marginal_demand >= max_marginal_sales - max_marginal_purchases:
                for order, _ in self.get_marginal_orders(time, area, spot_price, local_accepted_powers):
                    if order.order_type == OrderType.Sell:
                        local_accepted_powers[order.id] = order.q_max
                sharable_purchase_power = max_marginal_sales - marginal_demand
            else:
                for order, _ in self.get_marginal_orders(time, area, spot_price, local_accepted_powers):
                    if order.order_type == OrderType.Buy:
                        local_accepted_powers[order.id] = order.q_max
                sharable_sale_power = max_marginal_purchases + marginal_demand

            if sharable_purchase_power is not None:
                for order, _ in self.get_marginal_orders(time, area, spot_price, local_accepted_powers):
                    if order.order_type == OrderType.Buy and max_marginal_purchases * (order.q_max - order.q_min) != 0:
                        local_accepted_powers[order.id] = (
                                order.q_min
                                + sharable_purchase_power / max_marginal_purchases * (order.q_max - order.q_min)
                        )
            else:
                for order, _ in self.get_marginal_orders(time, area, spot_price, local_accepted_powers):
                    if order.order_type == OrderType.Sell and max_marginal_sales * (order.q_max - order.q_min) != 0:
                        local_accepted_powers[order.id] = (
                                order.q_min
                                + sharable_sale_power / max_marginal_sales * (order.q_max - order.q_min)
                        )

    def get_marginal_orders(self, current_time, market_area, spot_price, local_accepted_powers) -> list[MCOrder]:
        """Generator selecting marginal orders that can be involved in the redistribution process

        :param current_time: Result of optimization
        :type current_time:
        :param market_area: Result of optimization
        :type market_area:
        :param spot_price: Result of optimization
        :type spot_price:
        :param local_accepted_powers: Result of optimization
        :type local_accepted_powers:
        :return: A generator of MCOrder that may be updated
        :rtype: list[MCOrder]
        """
        for order in self.input_dataset.orders_per_market_area[market_area.name]:
            if not order.start_datetime <= current_time < order.end_date_processed:
                continue
            if order.duration > self.parameters.time_step:
                continue
            if order.price != spot_price:
                continue
            if order.name in self.get_order_names_in_order_couplings():
                continue
            accepted_power = local_accepted_powers[order.id]
            if order.q_min == 0.0 or (order.q_max != order.q_min and accepted_power != 0.0):
                # TODO: return only order
                yield order, accepted_power

    def get_order_names_in_order_couplings(self):
        return [order.name for order_coupling in self.input_dataset.order_couplings for order in order_coupling.orders]
