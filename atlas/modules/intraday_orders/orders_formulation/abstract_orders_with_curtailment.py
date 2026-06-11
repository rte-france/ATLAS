"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import TypeVar

from pendulum import DateTime

from atlas import Order, OrderCoupling, Timeseries
from atlas.enums import OrderType
from atlas.modules.intraday_orders.input_objects.solar import SolarIDO
from atlas.modules.intraday_orders.input_objects.wind import WindIDO
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import AbstractOrdersFormulator
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import build_intraday_order

R = TypeVar("R", bound=SolarIDO | WindIDO)


class AbstractOrdersFormulatorWithCurtailment(AbstractOrdersFormulator[R]):
    ORDER_NAME_TEMPLATE: str
    CURTAILMENT_ORDER_NAME_TEMPLATE: str

    def formulate_equipment_orders(
        self,
        equipment: R,
        orders_timestamps: list[DateTime],
        buy_submitted_volume: Timeseries,
        sell_submitted_volume: Timeseries,
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling]]:
        orders: list[Order] = []

        production_new_planing = equipment.maximum_power_forecast.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
        )
        production_engagement = equipment.da_cleared_quantity + equipment.total_id_cleared_quantity

        production_forecast = production_new_planing - production_engagement

        production_available_for_curtailment = production_engagement - production_new_planing * (
            1 - equipment.maximum_curtailment_ratio
        )

        variable_costs = None
        if equipment.variable_cost is not None:
            variable_costs = equipment.variable_cost.filter(item=orders_timestamps, inplace=False)

        if equipment.portfolio.market_area.id_price_forecast is None:
            return orders, []

        price_forecast = equipment.portfolio.market_area.id_price_forecast.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
        )

        for t in orders_timestamps:
            buy_isp_forecast = price_forecast.get_value(t) * (1.0 + parameters.large_imbalance_penalty)
            production_value = production_forecast.get_value(t)
            curtailment_value = production_available_for_curtailment.get_value(t)

            bid_name = self.ORDER_NAME_TEMPLATE.format(
                parameters.temporal.execution_date.format("YYYY_MM_DD_HH_mm_ss"),
                equipment.name,
                t.format("YYYY_MM_DD_HH_mm_ss"),
            )
            curtailment_bid_name = self.CURTAILMENT_ORDER_NAME_TEMPLATE.format(
                parameters.temporal.execution_date.format("YYYY_MM_DD_HH_mm_ss"),
                equipment.name,
                t.format("YYYY_MM_DD_HH_mm_ss"),
            )

            if abs(curtailment_value) >= parameters.allowed_round_off_error:
                if curtailment_value < 0:
                    curtailment_bid_output = build_intraday_order(
                        equipment, curtailment_bid_name, 0.0, 0.0, abs(curtailment_value), OrderType.Sell, t, parameters
                    )
                    orders.append(curtailment_bid_output)
                    sell_submitted_volume.sum_value_at(t, abs(curtailment_value))
                else:
                    curtailment_bid_output = build_intraday_order(
                        equipment, curtailment_bid_name, 0.0, 0.0, abs(curtailment_value), OrderType.Buy, t, parameters
                    )
                    orders.append(curtailment_bid_output)
                    buy_submitted_volume.sum_value_at(t, abs(curtailment_value))

            if abs(production_value) <= parameters.allowed_round_off_error:
                continue

            if production_value > 0:
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
                orders.append(bid_output)
                sell_submitted_volume.sum_value_at(t, abs(curtailment_value))

            if production_value < 0:
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
                orders.append(bid_output)
                sell_submitted_volume.sum_value_at(t, abs(curtailment_value))

        return orders, []
