"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic_extra_types.pendulum_dt import DateTime

from atlas import Order
from atlas.enum import Product, OrderType
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.tools.Utilities import Utilities
import atlas.config as cfg


class NonDispatchable:
    @staticmethod
    def formulate_non_dispatchable_orders(
        dataset: DayAheadOrdersInputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ) -> None:
        """
        This function formulates non dispatchable offers. Offers are priced at the variable cost
        `PropCost`, which is an attribute of these non dispatchable units. This can be assimilated
        to a `plug-in` strategy implied by a "à la Bertrand" market structure (competition through prices)

        For all bids, Qmin = 0 and Qmax corresponds to the production forecast at the time for wich
        the offer is made.

        If for example one wants to see the impact of having both negative and null prices on the offers,
        then one should create a unit with a negative `PropCost` and another with a `PropCost` equal to zero.

        Arguments:
        - `dataset`: a dataset
        - `orders_time`: a list of dates at which orders must be formulated.
        - `p`: a named tuple of subclass 'Parameters_List' containing the common parameters.
        """

        # Loop over the market players first.
        for unit in dataset.other_non_dispatchable:
            # Extract the forecasting matrix of the current actor.
            production_forecast = unit.maximum_power_forecast.get_forecast(
                parameters.execution_date,
                parameters.start_date,
                parameters.end_date.subtract(minutes=parameters.time_step),
            )

            if unit.da_sell_submitted_volume is None:
                unit.da_sell_submitted_volume = production_forecast
            else:
                unit.da_sell_submitted_volume.__add__(production_forecast)

            # Extract the sequence of variable costs that will be used to define the price.
            if unit.variable_cost is None:
                cfg.logger.debug("variable_cost is None for unit " + unit.name)
            else:
                variable_costs = unit.variable_cost.filter(item=orders_time, inplace=False)

                # Now we loop over the time stamps for which we want an offer to be made.
                # We formulate as many offers as there are time stamps in orders_time.
                for t in orders_time:
                    # Assign a unique name.
                    bid_name = "otherND_order_at_{}_for_unit_{}".format(
                        Utilities.get_date_to_clean_string(t), unit.Name
                    )

                    # Initialize the order object
                    bid_output = Order(name=bid_name)

                    # Fill the offer with the desired parameters.
                    bid_output.market_area = unit.portfolio.market_area
                    bid_output.portfolio = unit.portfolio
                    bid_output.equipment = unit
                    bid_output.qmax = production_forecast.get_value(t)
                    bid_output.qmin = 0
                    bid_output.price = variable_costs.get_value(t)
                    bid_output.product = Product.DayAhead
                    bid_output.order_type = OrderType.Sell
                    bid_output.is_agent_tso = False
                    bid_output.execution_date = parameters.execution_date
                    bid_output.start_date = t
                    bid_output.end_date = t.add(minutes=parameters.time_step)
                    dataset.order.append(bid_output)

        return None
