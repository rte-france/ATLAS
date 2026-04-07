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


class WindPVStep:
    @staticmethod
    def formulate_wind_and_pv_orders(
        dataset: DayAheadOrdersOutput, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ) -> None:
        """
        This function formulates wind and pv orders for all solar and wind equipments. For each order:
            _ The price corresponds to the variable cost of each equipment (possibly negative).
            _ Qmax corresponds to the generation forecast, extracted from MaximumPowerForecast at
              the execution_date for which the order is made.
            _ Qmin corresponds to a ratio of Qmax given by the property MaximumCurtailmentRatio.

        :param dataset: the dataset
        :type dataset: DayAheadOrdersOutput
        :param orders_time: a list of dates over which orders will be formulated.
        :type orders_time: list[DateTime]
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        :return: None
        """

        # Retrieve all wind and solar equipments from the dataset.
        equipments_list = dataset.wind + dataset.solar

        # Loop over all these equipments.
        for equipment in equipments_list:
            # Extract the maximum_power_forecast matrix for the current equipment.
            if equipment.maximum_power_forecast is None:
                cfg.logger.warning(f"maximum_power_forecast is None for wind/photovoltaic {equipment.name}")
            else:
                production_forecast = equipment.maximum_power_forecast.get_forecast(
                    parameters.temporal.execution_date,
                    parameters.temporal.start_date,
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

                for t in orders_time:
                    bid_name = f"order_at_{t}_for_unit_{equipment.name}"

                    # Extract the available generation level range
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
                            price=0.0 if variable_costs is None else variable_costs.get_value(t),
                            product=Product.DayAhead,
                            order_type=OrderType.Sell,
                            is_agent_tso=False,
                            execution_date=parameters.temporal.execution_date,
                            start_date=t,
                            end_date=t + parameters.temporal.timestep,
                        )
                        dataset.order.append(bid_output)
