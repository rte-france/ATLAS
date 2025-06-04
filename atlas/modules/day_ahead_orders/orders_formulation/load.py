"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.modules.day_ahead_orders.tools.Utilities import Utilities


class Load:
    @staticmethod
    def formulate_load_orders(dataset, orders_time, p) -> None:
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
        for l in dataset.Load.instances.values():
            # Extract the forecasting matrix of the current actor.
            consumption_forecast = l.MaximumPowerForecast.GetForecast(
                p.execution_date, p.start_date, p.end_date.AddMinutes(-p.time_step)
            )
            l.DABuySubmittedVolume += (
                consumption_forecast.Abs()
            )  # TODO : "Converts each value in the timeseries into its absolute value and returns it."

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
                        bid_output.Price = l.VariableCost.GetValue(t)
                    else:
                        bid_output.Price = p.consumption_price
                    bid_output.Product = "DayAhead"
                    bid_output.OrderType = "Buy"
                    bid_output.IsAgentTSO = False
                    bid_output.ExecutionDate = str(p.execution_date)
                    bid_output.StartDate = str(t)
                    bid_output.EndDate = str(t.AddMinutes(p.time_step))
