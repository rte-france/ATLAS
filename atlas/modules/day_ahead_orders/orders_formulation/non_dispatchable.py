"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic_extra_types.pendulum_dt import DateTime

from atlas import Order
from atlas.enum import OrderType, Product
from atlas.modules.day_ahead_orders.dao_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.dao_parameters import DayAheadOrdersParameters


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
        - `parameters` a named tuple of parameters, containing the common parameters.
        """

        # Loop over the market players first.
        for unit in dataset.other_non_dispatchable:
            # Extract the forecasting matrix of the current actor.
            production_forecast = unit.maximum_power_forecast.get_forecast(
                parameters.execution_date,
                parameters.start_date,
                parameters.penultimate_date,
                parameters.time_step,
            )

            if unit.da_sell_submitted_volume is None:
                unit.da_sell_submitted_volume = production_forecast
            else:
                unit.da_sell_submitted_volume += production_forecast

            # Extract the sequence of variable costs that will be used to define the price.
            variable_costs = None
            if unit.variable_cost is not None:
                variable_costs = unit.variable_cost.filter(item=orders_time, inplace=False)

            # Now we loop over the time stamps for which we want an offer to be made.
            # We formulate as many offers as there are time stamps in orders_time.
            for t in orders_time:
                # Initialize the order object
                bid_output = Order(
                    name=f"otherND_order_at_{t}_for_unit_{unit.name}",  # Assign a unique name.
                    market_area=unit.portfolio.market_area,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=production_forecast.get_value(t),
                    qmin=0,
                    price=0.0 if variable_costs is None else variable_costs.get_value(t),
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=parameters.execution_date,
                    start_date=t,
                    end_date=t + parameters.time_step,
                )
                dataset.order.append(bid_output)
