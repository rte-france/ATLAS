"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import List, TypeVar

from pendulum import DateTime

from atlas import Timeseries, Solar, Wind
from atlas.enums import OrderType
from atlas.modules.intraday_orders.orders_formulation.abstract_orders_formulator import AbstractOrdersFormulator
from atlas.modules.intraday_orders.output_dataset import IntradayOrdersOutputDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import get_date_to_clean_string, build_intraday_order

R = TypeVar("R", bound=Solar | Wind)


class AbstractOrdersFormulatorWithCurtailment(AbstractOrdersFormulator[R]):
    ORDER_NAME_TEMPLATE: str
    CURTAILMENT_ORDER_NAME_TEMPLATE: str

    def formulate_equipment_orders(
        self,
        equipment: R,
        orders_timestamps: List[DateTime],
        buy_submitted_volume: Timeseries,
        sell_submitted_volume: Timeseries,
        dataset: IntradayOrdersOutputDataset,
        parameters: IntradayOrdersParameters,
    ):
        # Extract the forecasting matrix of the current actor
        production_new_planing = equipment.maximum_power_forecast.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_date
        )
        production_engagement = equipment.da_cleared_quantity + equipment.total_id_cleared_quantity

        production_forecast = production_new_planing - production_engagement

        production_available_for_curtailment = production_engagement - production_new_planing * (
            1 - equipment.maximum_curtailment_ratio
        )

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
            buy_isp_forecast = price_forecast.get_value(t) * (1.0 + parameters.large_imbalance_penalty)
            production_value = production_forecast.get_value(t)
            curtailment_value = production_available_for_curtailment.get_value(t)

            bid_name = self.ORDER_NAME_TEMPLATE.format(
                get_date_to_clean_string(parameters.execution_date), equipment.name, get_date_to_clean_string(t)
            )
            curtailment_bid_name = self.CURTAILMENT_ORDER_NAME_TEMPLATE.format(
                get_date_to_clean_string(parameters.execution_date), equipment.name, get_date_to_clean_string(t)
            )

            # Curtailment
            if abs(curtailment_value) >= parameters.allowed_round_off_error:
                if curtailment_value < 0:
                    # Previous engagements are lower than possible curtailment capacity, hence an offer at all cost
                    curtailment_bid_output = build_intraday_order(
                        equipment,
                        curtailment_bid_name,
                        0.0,
                        0.0,
                        abs(curtailment_value),
                        OrderType.Sell,
                        t,
                        parameters,
                    )
                    dataset.add_order(curtailment_bid_output)
                    sell_submitted_volume.sum_value_at(t, abs(curtailment_value))

                else:
                    # Previous engagements are non-limiting, and the unit offers available margin as curtailment
                    curtailment_bid_output = build_intraday_order(
                        equipment,
                        curtailment_bid_name,
                        0.0,
                        0.0,
                        abs(curtailment_value),
                        OrderType.Buy,
                        t,
                        parameters,
                    )
                    dataset.add_order(curtailment_bid_output)
                    buy_submitted_volume.sum_value_at(t, abs(curtailment_value))

            if abs(production_value) <= parameters.allowed_round_off_error:
                continue

            if production_value > 0:
                # Production is greater than previously cleared
                bid_output = build_intraday_order(
                    equipment,
                    bid_name,
                    variable_costs.get_value(t),
                    0.0,
                    abs(production_value),
                    OrderType.Sell,
                    t,
                    parameters,
                )
                dataset.add_order(bid_output)
                sell_submitted_volume.sum_value_at(t, abs(curtailment_value))

            if production_value < 0:
                # Production is lower than previously cleared
                # Unit buys back the sold surplus if market prices are lower than forecasted imbalance price
                bid_output = build_intraday_order(
                    equipment,
                    bid_name,
                    variable_costs.get_value(t) + buy_isp_forecast,
                    0.0,
                    abs(production_value),
                    OrderType.Sell,
                    t,
                    parameters,
                )
                dataset.add_order(bid_output)
                sell_submitted_volume.sum_value_at(t, abs(curtailment_value))
