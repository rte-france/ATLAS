"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas import Order
from atlas.enum import OrderType, Product
from atlas.modules.day_ahead_orders.dao_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.dao_parameters import DayAheadOrdersParameters


class WindPV:
    @staticmethod
    def formulate_wind_and_pv_orders(
        dataset: DayAheadOrdersInputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ) -> None:
        """
        This function formulates wind and pv orders. Orders are priced at the variable cost
        `PropCost`. This can be assimilated to a `plug-in` strategy implied by
        a "à la Bertrand" market structure (competition through prices).

        For all bids, Qmax corresponds to the production forecast at the time for wich
        the offer is made. Qmin corresponds to a ratio of Qmax given by the property MaximumCurtailmentRatio.

        Arguments:
        - `dataset`: a dataset
        - `orders_time`: a list of dates at which orders must be formulated.
        - `parameters` a named tuple of parameters, containing the common parameters.
        """

        # Extract the wind portfolios
        wind = dataset.wind
        photovoltaic = dataset.solar

        # Create a list of the different non dispatchable portfolios.
        # This crude loop appears to be the only method working with lists{DynamicInstance}
        equipments_list = wind + photovoltaic

        # Loop over the market players first.
        for equipment in equipments_list:
            # Extract the MaximumPowerForecast matrix of the current actor.
            production_forecast = equipment.maximum_power_forecast.get_forecast(
                parameters.execution_date,
                parameters.start_date,
                parameters.penultimate_date,
            )
            if equipment.da_sell_submitted_volume is None:
                equipment.da_sell_submitted_volume = production_forecast
            else:
                equipment.da_sell_submitted_volume += production_forecast

            # Extract the sequence of variable costs that will be used to define the price.
            variable_costs = None
            if equipment.variable_cost is not None:
                variable_costs = equipment.variable_cost.filter(orders_time, inplace=False)

            # Now we loop over the time stamps for which we want an offer to be made.
            # We formulate as many offers as there are time stamps in orders_time.
            for t in orders_time:
                # Assign a unique name
                bid_name = ""
                if type(equipment).__name__ == "Wind":
                    bid_name = f"wind_order_at_{t}_for_unit_{equipment.name}"
                elif type(equipment).__name__ == "Solar":
                    bid_name = f"pv_order_at_{t}_for_unit_{equipment.name}"
                else:
                    cfg.logger.warning(f"equipment {equipment.name} isn't Wind nor Solar")

                # Extract the available production level range
                max_production_value = production_forecast.get_value(t)
                min_production_value = max_production_value * (1 - equipment.maximum_curtailment_ratio.get_value(t))

                if max_production_value > 0:
                    # Initialize the order object
                    bid_output = Order(
                        name=bid_name,
                        market_area=equipment.portfolio.market_area,
                        portfolio=equipment.portfolio,
                        equipment=equipment,
                        qmax=max_production_value,
                        qmin=min_production_value,
                        price=0.0
                        if variable_costs is None
                        else variable_costs.get_value(t),  # Extract the PropCpst that will define the price.
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=str(parameters.execution_date),
                        start_date=str(t),
                        end_date=str(t + parameters.time_step),
                    )
                    dataset.order.append(bid_output)
