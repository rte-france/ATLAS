"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import OrderType, Product
from atlas.modules.day_ahead_orders.models.order import OrderDAO
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.timing import bmo_name_datetime_to_str


class NonDispatchableStep:
    @staticmethod
    def formulate_non_dispatchable_orders(
        dataset: DayAheadOrdersOutput, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ) -> None:
        """
        This function formulates non dispatchable offers. Offers are priced at the variable cost
        `PropCost`, which is an attribute of these non dispatchable units. This can be assimilated
        to a `plug-in` strategy implied by a "à la Bertrand" market structure (competition through prices)

        For all bids, Qmin = 0 and Qmax corresponds to the production forecast at the time for wich
        the offer is made.

        If for example one wants to see the impact of having both negative and null prices on the offers,
        then one should create a unit with a negative `PropCost` and another with a `PropCost` equal to zero.

        :param dataset: the dataset
        :type dataset: DayAheadOrdersOutput
        :param orders_time: a list of dates over which orders will be formulated.
        :type orders_time: list[DateTime]
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        :return: None
        """

        # Loop over the market players first.
        for unit in dataset.other_non_dispatchable:
            # Extract the forecasting matrix of the current actor.
            if unit.maximum_power_forecast is None:
                cfg.logger.warning(f"maximum_power_forecast is None for other_non_dispatchable {unit.name}")
            else:
                production_forecast = unit.maximum_power_forecast.get_forecast(
                    parameters.execution_date,
                    parameters.start_date,
                    parameters.penultimate_date,
                    parameters.timestep,
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
                    bid_output = OrderDAO(
                        name=f"otherND_order_at_{bmo_name_datetime_to_str(t)}_for_unit_{unit.name}",  # Assign a unique name.
                        market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
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
                        end_date=t + parameters.timestep,
                    )
                    dataset.order.append(bid_output)
