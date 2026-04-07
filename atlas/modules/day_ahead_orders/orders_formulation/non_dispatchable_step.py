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


class NonDispatchableStep:
    @staticmethod
    def formulate_non_dispatchable_orders(
        dataset: DayAheadOrdersOutput, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ) -> None:
        """
        This function formulates orders for all non dispatchable equipments, for each time job in orders_time.
        For each order:
            _ Qmin = 0 and Qmax corresponds to the generation forecast at the associated time job,
              which is stored in the maximum_power_forecast matrix of the equipment.
              As we deal with non_dispatchable generation, the volume is assumed to be non curtailable.
            _ The price is extracted from the variable_cost attribute of the equipment.

        The function takes the following arguments:
        :param dataset: the dataset
        :type dataset: DayAheadOrdersOutput
        :param orders_time: a list of dates over which orders will be formulated.
        :type orders_time: list[DateTime]
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        :return: None
        """

        # Loop over all other non dispatchable equipments first
        for unit in dataset.other_non_dispatchable:
            # Extract the generation forecast of the current equipment
            if unit.maximum_power_forecast is None:
                cfg.logger.warning(f"maximum_power_forecast is None for other_non_dispatchable {unit.name}")
            else:
                production_forecast = unit.maximum_power_forecast.get_forecast(
                    parameters.temporal.execution_date,
                    parameters.temporal.start_date,
                    parameters.penultimate_date,
                    parameters.temporal.timestep,
                )

                if unit.da_sell_submitted_volume is None:
                    unit.da_sell_submitted_volume = production_forecast
                else:
                    unit.da_sell_submitted_volume += production_forecast

                # Extract the sequence of variable costs that will be used to define the price.
                variable_costs = None
                if unit.variable_cost is not None:
                    variable_costs = unit.variable_cost.filter(item=orders_time, inplace=False)

                # Loop over the time steps of orders_time, and formulate a separate orders for each one
                for t in orders_time:
                    bid_output = OrderDAO(
                        name=f"otherND_order_at_{t}_for_unit_{unit.name}",  # Assign a unique name.
                        market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=production_forecast.get_value(t),
                        qmin=0,
                        price=0.0 if variable_costs is None else variable_costs.get_value(t),
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=parameters.temporal.execution_date,
                        start_date=t,
                        end_date=t + parameters.temporal.timestep,
                    )
                    dataset.order.append(bid_output)
