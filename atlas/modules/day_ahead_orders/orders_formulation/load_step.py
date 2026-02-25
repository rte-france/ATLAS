"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas import Timeseries
from atlas.enums import LoadType, OrderType, Product
from atlas.modules.day_ahead_orders.data_models.order import OrderDAO
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.timing import bmo_name_datetime_to_str


class LoadStep:
    @staticmethod
    def formulate_load_orders(
        dataset: DayAheadOrdersOutput, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ) -> None:
        """
        Formulates consumption bids on the spot market.
        Uses the parameters specified by the user and the dataset to create bids based on the forecast
        stored in the Power forecasting matrix of a "Load" equipment.

        The function takes the following arguments:
        :param dataset: the dataset
        :type dataset: DayAheadOrdersOutput
        :param orders_time: a list of dates over which orders will be formulated.
        :type orders_time: list[DateTime]
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        :return: None
        """

        # Loop over the market players first
        for load in dataset.load:
            if load.maximum_power_forecast is None:
                cfg.logger.warning(f"maximum_power_forecast is None for load {load.name}, {load.load_type}")
            else:
                # Extract the forecasting matrix of the current actor.
                consumption_forecast = load.maximum_power_forecast.get_forecast(
                    parameters.execution_date,
                    parameters.start_date,
                    parameters.penultimate_date,
                    parameters.timestep,
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
                            bid_output = OrderDAO(
                                name=f"load_order_at_{bmo_name_datetime_to_str(t)}_for_unit_{load.name}",
                                market_area=load.portfolio.market_area,
                                portfolio=load.portfolio,
                                equipment=load,
                                qmax=max_consumption_value,
                                qmin=0,
                                product=Product.DayAhead,
                                order_type=OrderType.Buy,
                                is_agent_tso=False,
                                execution_date=parameters.execution_date,
                                start_date=t,
                                end_date=t + parameters.timestep,
                                price=load.variable_cost.get_value(t)
                                if load.load_type == LoadType.POWER_TO_GAS
                                else parameters.load_price,
                            )
                            dataset.order.append(bid_output)
