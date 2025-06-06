"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import datetime, timedelta

from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.tools.Utilities import Utilities


class Load:
    @staticmethod
    def formulate_load_orders(
        dataset: DayAheadOrdersInputDataset, orders_time: list[datetime], parameters: DayAheadOrdersParameters
    ) -> None:
        """
        Formulates consumption bids on the spot market.
        Uses the parameters specified by the user and the input marker to create bids based on the forecast
        stored in the Power forecasting matrix of a "Load" equipement.

        The function takes the following arguments:

        - `dataset`: a dataset.
        - `orders_time`: a list of dates at which orders must be formulated.
        - `p` a named tuple of parameters, containing the common parameters.
        """

        # Loop over the market players first
        for l in dataset.raw_data["load"]:
            # Extract the forecasting matrix of the current actor.
            consumption_forecast = l.maximum_power_forecast.get_forecast(
                parameters.execution_date,
                parameters.start_date,
                parameters.end_date - timedelta(minutes=parameters.time_step),
            )
            l.da_buy_submitted_volume += consumption_forecast.abs()

            # Now we loop over the time stamps for which we want an offer to be made.
            # We formulate as many offers as there are time stamps in orders_time.
            for t in orders_time:
                # Extract the desired consumption level.
                max_consumption_value = abs(consumption_forecast.get_value(t))

                # Formulate an order if max_consumption_value is strictly positive
                if max_consumption_value > 0:
                    # Initialize the order object.
                    bid_output = dataset.Order.CreateInstance(
                        "load_order_at_{}_for_unit_{}".format(Utilities.get_date_to_clean_string(t), l.Name)
                    )

                    # Fill the offer with the desired parameters.
                    bid_output.MarketArea = l.Portfolio.MarketArea
                    bid_output.Portfolio = l.Portfolio
                    bid_output.Equipment = l
                    bid_output.Qmax = max_consumption_value
                    bid_output.Qmin = 0
                    if l.LoadType == "PowerToGas":
                        bid_output.Price = l.VariableCost.get_value(t)
                    else:
                        bid_output.Price = parameters.consumption_price
                    bid_output.Product = "DayAhead"
                    bid_output.OrderType = "Buy"
                    bid_output.IsAgentTSO = False
                    bid_output.ExecutionDate = str(parameters.execution_date)
                    bid_output.StartDate = str(t)
                    bid_output.EndDate = str(t + parameters.time_step)
