"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import List

from pendulum import DateTime

from atlas import OtherNonDispatchable, Timeseries
from atlas.enums import OrderType
from atlas.modules.intraday_orders.orders_formulation.abstract_orders_formulator import AbstractOrdersFormulator
from atlas.modules.intraday_orders.output_dataset import IntradayOrdersOutputDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import get_date_to_clean_string, build_intraday_order


class NonDispatchableOrdersFormulator(AbstractOrdersFormulator[OtherNonDispatchable]):
    ORDER_NAME_TEMPLATE = "otherND_IDOrder_{}_{}_{}"

    def formulate_orders(
        self,
        equipments: List[OtherNonDispatchable],
        orders_timestamps: List[DateTime],
        dataset: IntradayOrdersOutputDataset,
        parameters: IntradayOrdersParameters,
    ):
        for equipment in equipments:
            sell_submitted_volume = Timeseries.from_index(
                parameters.start_date, parameters.timestep, parameters.penultimate_date, 0
            )
            buy_submitted_volume = Timeseries.from_index(
                parameters.start_date, parameters.timestep, parameters.penultimate_date, 0
            )

            # Extract the forecasting matrix of the current actor
            production_new_planing = equipment.maximum_power_forecast.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            )
            production_engagement = equipment.da_cleared_quantity + equipment.total_id_cleared_quantity

            production_forecast = production_new_planing - production_engagement

            # Extract the sequence of variable costs that will be used to define the price.
            variable_costs = None
            if equipment.variable_cost is not None:
                variable_costs = equipment.variable_cost.filter(item=orders_timestamps, inplace=False)

            # Extract the area price forecast
            price_forecast = equipment.portfolio.market_area.id_price_forecast.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            )

            # Now we loop over the time stamps for which we want an offer to be made.
            # We formulate as many offers as there are time stamps in orders_time.
            for t in orders_timestamps:
                bid_name = self.ORDER_NAME_TEMPLATE.format(
                    get_date_to_clean_string(parameters.execution_date), equipment.name, get_date_to_clean_string(t)
                )

                # Extract the desired production level
                production_value = production_forecast.get_value(t)

                buy_isp_forecast = price_forecast.get_value(t) * (1.0 + parameters.large_imbalance_penalty)

                if abs(production_value) <= parameters.allowed_round_off_error:
                    continue

                if production_value > 0:
                    order_type = OrderType.Sell
                    price = variable_costs.get_value(t)
                    sell_submitted_volume.sum_value_at(t, abs(production_value))

                else:
                    order_type = OrderType.Buy
                    price = variable_costs.get_value(t) + buy_isp_forecast
                    buy_submitted_volume.sum_value_at(t, abs(production_value))

                bid_output = build_intraday_order(
                    equipment, bid_name, price, 0.0, abs(production_value), order_type, t, parameters
                )
                dataset.add_order(bid_output)

            equipment.id_buy_submitted_volume.add(buy_submitted_volume, parameters.execution_date)
            equipment.id_sell_submitted_volume.add(sell_submitted_volume, parameters.execution_date)

            equipment.total_id_buy_submitted_volume += buy_submitted_volume
            equipment.total_id_sell_submitted_volume += sell_submitted_volume

        return None
