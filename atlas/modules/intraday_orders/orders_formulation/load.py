"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas import Timeseries
from atlas.enums import LoadType, OrderType
from atlas.modules.intraday_orders.input_objects.load import LoadIDO
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import AbstractOrdersFormulator
from atlas.modules.intraday_orders.output_dataset import IntradayOrdersOutputDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import build_intraday_order, get_date_to_clean_string


class LoadOrdersFormulator(AbstractOrdersFormulator[LoadIDO]):
    EQUIPMENT_TYPE_NAME = "load"

    def formulate_equipment_orders(
        self,
        equipment: LoadIDO,
        orders_timestamps: list[DateTime],
        buy_submitted_volume: Timeseries,
        sell_submitted_volume: Timeseries,
        dataset: IntradayOrdersOutputDataset,
        parameters: IntradayOrdersParameters,
    ):
        consumption_engagement = equipment.da_cleared_quantity + equipment.total_id_cleared_quantity

        if equipment.load_type == LoadType.POWER_TO_GAS:
            # Power-to-Gas offers all available capacity (up and down) at its marginal price
            # Up to two orders (Buy and Sell)

            # maximum_power < 0 by convention
            maximum_power = equipment.maximum_power_forecast.get_forecast(
                parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
            )

            available_power = consumption_engagement - maximum_power

            for t in orders_timestamps:
                available_down_power = available_power.get_value(t)
                available_up_power = consumption_engagement.get_value(t)

                if available_down_power > parameters.allowed_round_off_error:
                    bid_output = self.build_offer(
                        equipment,
                        equipment.variable_cost.get_value(t),
                        available_down_power,
                        OrderType.Buy,
                        t,
                        parameters,
                    )
                    dataset.add_order(bid_output)
                    buy_submitted_volume.sum_value_at(t, abs(available_down_power))

                if abs(available_up_power) > parameters.allowed_round_off_error:
                    bid_output = self.build_offer(
                        equipment,
                        equipment.variable_cost.get_value(t),
                        available_up_power,
                        OrderType.Sell,
                        t,
                        parameters,
                    )
                    dataset.add_order(bid_output)
                    sell_submitted_volume.sum_value_at(t, abs(available_up_power))

        else:
            # Baseload and OtherNonDispatchable only wish to balance
            # Only one order (Buy or Sell)

            consumption_new_planing = equipment.maximum_power_forecast.get_forecast(
                parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
            )

            consumption_forecast = consumption_engagement - consumption_new_planing

            # Now we loop over the timestamps for which we want an offer to be made
            # We formulate as many offers as there are timestamps in orders_time
            for t in orders_timestamps:
                # Extract the desired consumption level.
                consumption_value = consumption_forecast.get_value(t)

                if consumption_value > parameters.allowed_round_off_error:
                    bid_output = self.build_offer(
                        equipment, parameters.consumption_price, consumption_value, OrderType.Buy, t, parameters
                    )
                    dataset.add_order(bid_output)
                    buy_submitted_volume.sum_value_at(t, abs(consumption_value))

                elif abs(consumption_value) > parameters.allowed_round_off_error:
                    bid_output = self.build_offer(equipment, 0.0, consumption_value, OrderType.Sell, t, parameters)
                    dataset.add_order(bid_output)
                    sell_submitted_volume.sum_value_at(t, abs(consumption_value))

    def build_offer(
        self,
        equipment: LoadIDO,
        price: float,
        qmax: float,
        order_type: OrderType,
        time: DateTime,
        parameters: IntradayOrdersParameters,
    ):
        bid_name = f"{order_type.value}_IDOrder_{get_date_to_clean_string(parameters.temporal.execution_date)}_{equipment.name}_{get_date_to_clean_string(time)}"
        return build_intraday_order(
            equipment,
            bid_name,
            price,
            0.0,
            qmax,
            order_type,
            time,
            parameters,
        )
