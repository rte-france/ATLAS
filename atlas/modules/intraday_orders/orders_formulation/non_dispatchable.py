"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas import OtherNonDispatchable, Timeseries
from atlas.enums import OrderType
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import AbstractOrdersFormulator
from atlas.modules.intraday_orders.output_dataset import IntradayOrdersOutputDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import build_intraday_order, get_date_to_clean_string


class NonDispatchableOrdersFormulator(AbstractOrdersFormulator[OtherNonDispatchable]):
    EQUIPMENT_TYPE_NAME = "non-dispatchable"

    def formulate_equipment_orders(
        self,
        equipment: OtherNonDispatchable,
        orders_timestamps: list[DateTime],
        buy_submitted_volume: Timeseries,
        sell_submitted_volume: Timeseries,
        dataset: IntradayOrdersOutputDataset,
        parameters: IntradayOrdersParameters,
    ):
        # Extract the forecasting matrix of the current actor
        production_new_planing = equipment.maximum_power_forecast.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
        )
        production_engagement = equipment.da_cleared_quantity + equipment.total_id_cleared_quantity

        production_forecast = production_new_planing - production_engagement

        # Extract the sequence of variable costs that will be used to define the price.
        variable_costs = None
        if equipment.variable_cost is not None:
            variable_costs = equipment.variable_cost.filter(item=orders_timestamps, inplace=False)

        # Extract the area price forecast
        price_forecast = equipment.portfolio.market_area.id_price_forecast.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
        )

        # Now we loop over the time stamps for which we want an offer to be made.
        # We formulate as many offers as there are time stamps in orders_time.
        for t in orders_timestamps:
            bid_name = f"otherND_IDOrder_{get_date_to_clean_string(parameters.temporal.execution_date)}_{equipment.name}_{get_date_to_clean_string(t)}"

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
