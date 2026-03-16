"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas import Solar, Wind
from atlas.enums import OrderType, Product
from atlas.modules.day_ahead_orders.models.order import OrderDAO
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters


class WindPVStep:
    @staticmethod
    def formulate_wind_and_pv_orders(
        dataset: DayAheadOrdersOutput, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ) -> None:
        """
        This function formulates wind and pv orders. Orders are priced at the variable cost
        `PropCost`. This can be assimilated to a `plug-in` strategy implied by
        a "à la Bertrand" market structure (competition through prices).

        For all bids, Qmax corresponds to the production forecast at the time for wich
        the offer is made. Qmin corresponds to a ratio of Qmax given by the property MaximumCurtailmentRatio.

        :param dataset: the dataset
        :type dataset: DayAheadOrdersOutput
        :param orders_time: a list of dates over which orders will be formulated.
        :type orders_time: list[DateTime]
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        :return: None
        """

        # Create a list of the different non dispatchable portfolios.
        equipments_list = dataset.wind + dataset.solar

        # Loop over the market players first.
        for equipment in equipments_list:
            # Extract the maximum_power_forecast matrix of the current actor.
            if equipment.maximum_power_forecast is None:
                cfg.logger.warning(f"maximum_power_forecast is None for wind/photovoltaic {equipment.name}")
            else:
                production_forecast = equipment.maximum_power_forecast.get_forecast(
                    parameters.date.execution_date,
                    parameters.date.start_date,
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
                    if isinstance(equipment, Wind):
                        bid_name = f"wind_order_at_{t}_for_unit_{equipment.name}"
                    elif isinstance(equipment, Solar):
                        bid_name = f"pv_order_at_{t}_for_unit_{equipment.name}"
                    else:
                        cfg.logger.warning(f"equipment {equipment.name} isn't Wind nor Solar")

                    # Extract the available production level range
                    max_production_value = production_forecast.get_value(t)
                    min_production_value = max_production_value * (1 - equipment.maximum_curtailment_ratio.get_value(t))

                    if max_production_value > 0:
                        bid_output = OrderDAO(
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
                            execution_date=parameters.date.execution_date,
                            start_date=t,
                            end_date=t + parameters.timestep,
                        )
                        dataset.order.append(bid_output)
