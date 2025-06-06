"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.modules.day_ahead_orders.tools.Utilities import Utilities


def formulate_non_dispatchable_orders(dataset, orders_time, p):
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
    for unit in dataset.OtherNonDispatchable.instances.values():
        # Extract the forecasting matrix of the current actor.
        production_forecast = unit.MaximumPowerForecast.get_forecast(
            p.execution_date, p.start_date, p.end_date - p.time_step
        )
        unit.DASellSubmittedVolume += production_forecast

        # Extract the sequence of variable costs that will be used to define the price.
        variable_costs = unit.VariableCost.Extract("", orders_time)

        # Now we loop over the time stamps for which we want an offer to be made.
        # We formulate as many offers as there are time stamps in orders_time.
        for t in orders_time:
            # Assign a unique name.
            bid_name = "otherND_order_at_{}_for_unit_{}".format(Utilities.get_date_to_clean_string(t), unit.Name)

            # Initialize the order object
            bid_output = dataset.Order.CreateInstance(bid_name)

            # Fill the offer with the desired parameters.
            bid_output.MarketArea = unit.Portfolio.MarketArea
            bid_output.Portfolio = unit.Portfolio
            bid_output.Equipment = unit
            bid_output.Qmax = production_forecast.get_value(t)
            bid_output.Qmin = 0
            bid_output.Price = variable_costs.get_value(t)
            bid_output.Product = "DayAhead"
            bid_output.OrderType = "Sell"
            bid_output.IsAgentTSO = False
            bid_output.ExecutionDate = str(p.execution_date)
            bid_output.StartDate = str(t)
            bid_output.EndDate = str(t + p.time_step)

    return None
