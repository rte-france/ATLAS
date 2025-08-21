"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas import Order, Timeseries
from atlas.enum import LoadType, OrderType, Product
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.tools.Utilities import Utilities


class DAOLoad:
    @staticmethod
    def formulate_load_orders(
        dataset: DayAheadOrdersInputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ) -> None:
        """
        Formulates consumption bids on the spot market.
        Uses the parameters specified by the user and the input marker to create bids based on the forecast
        stored in the Power forecasting matrix of a "Load" equipment.

        The function takes the following arguments:

        - `dataset`: a dataset.
        - `orders_time`: a list of dates at which orders must be formulated.
        - `parameters` a named tuple of parameters, containing the common parameters.
        """

        # Loop over the market players first
        for load in dataset.load:
            # Extract the forecasting matrix of the current actor.
            consumption_forecast = load.maximum_power_forecast.get_forecast(
                parameters.execution_date,
                parameters.start_date,
                parameters.end_date.subtract(minutes=parameters.time_step),
                pendulum.Duration(minutes=parameters.time_step),
            )

            if load.da_buy_submitted_volume is None:
                load.da_buy_submitted_volume = Timeseries(consumption_forecast.abs())
            else:
                load.da_buy_submitted_volume += consumption_forecast.abs()

            # Now we loop over the time stamps for which we want an offer to be made.
            # We formulate as many offers as there are time stamps in orders_time.
            for t in orders_time:
                # Extract the desired consumption level.
                if len(consumption_forecast) == 0:
                    cfg.logger.debug(f"consumption_forecast is empty for load {load.name}, {load.load_type}")
                else:
                    max_consumption_value = abs(consumption_forecast.get_value(t))

                    # Formulate an order if max_consumption_value is strictly positive
                    if max_consumption_value > 0:
                        # Initialize the order object.
                        bid_output = Order(
                            name=f"load_order_at_{Utilities.get_date_to_clean_string(t)}_for_unit_{load.name}"
                        )

                        # Fill the offer with the desired parameters.
                        bid_output.market_area = load.portfolio.market_area
                        bid_output.portfolio = load.portfolio
                        bid_output.equipment = load
                        bid_output.qmax = max_consumption_value
                        bid_output.qmin = 0
                        if load.load_type == LoadType.POWER_TO_GAS:
                            bid_output.price = load.variable_cost.get_value(t)
                        else:
                            bid_output.price = parameters.load_price
                        bid_output.product = Product.DayAhead
                        bid_output.order_type = OrderType.Buy
                        bid_output.is_agent_tso = False
                        bid_output.execution_date = parameters.execution_date
                        bid_output.start_date = t
                        bid_output.end_date = t.add(minutes=parameters.time_step)
                        dataset.order.append(bid_output)
