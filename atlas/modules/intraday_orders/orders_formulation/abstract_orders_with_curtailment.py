"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import TypeVar

from pendulum import DateTime

from atlas.enums import OrderType
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_orders.input_objects.solar import SolarIDO
from atlas.modules.intraday_orders.input_objects.wind import WindIDO
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import AbstractOrdersFormulator
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import build_intraday_order, engaged_quantity
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling

R = TypeVar("R", bound=SolarIDO | WindIDO)


class AbstractOrdersFormulatorWithCurtailment(AbstractOrdersFormulator[R]):
    ORDER_NAME_TEMPLATE: str
    CURTAILMENT_ORDER_NAME_TEMPLATE: str

    def formulate_equipment_orders(
        self,
        equipment: R,
        orders_timestamps: list[DateTime],
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling], Timeseries, Timeseries]:
        orders: list[Order] = []
        sell_values: list[float] = [0.0] * len(orders_timestamps)
        buy_values: list[float] = [0.0] * len(orders_timestamps)

        new_production_plan = equipment.maximum_power_forecast.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
        )
        cleared_position = engaged_quantity(equipment, parameters)

        # production_delta > 0: more production planned than cleared → sell the surplus.
        # production_delta < 0: less production planned than cleared → buy back the shortfall.
        production_delta = new_production_plan - cleared_position

        curtailment_ratio = equipment.maximum_curtailment_ratio.filter(item=orders_timestamps, inplace=False)

        # curtailment_delta = cleared_position - new_plan + new_plan * curtailment_ratio
        # < 0: curtailment margin available → sell (offer to reduce production at price 0)
        # > 0: committed to more curtailment than available → buy back the over-curtailed volume
        curtailment_delta = cleared_position - new_production_plan + new_production_plan * curtailment_ratio

        variable_costs = None
        if equipment.variable_cost is not None:
            variable_costs = equipment.variable_cost.filter(item=orders_timestamps, inplace=False)

        if equipment.portfolio.market_area.id_price_forecast is None:
            zero = Timeseries.from_index(
                parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, 0.0
            )
            return orders, [], zero, zero

        price_forecast = equipment.portfolio.market_area.id_price_forecast.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
        )

        for i, t in enumerate(orders_timestamps):
            # Imbalance penalty price: the cost of being caught short on the balancing market,
            # used to motivate buying back a shortfall even above marginal cost.
            imbalance_penalty_price = price_forecast.get_value(t) * (1.0 + parameters.large_imbalance_penalty)
            production_value = production_delta.get_value(t)
            curtailment_value = curtailment_delta.get_value(t)

            bid_name = self.ORDER_NAME_TEMPLATE.format(
                parameters.temporal.execution_date.format("DD_MM_YYYY_HH_mm_ss"),
                equipment.name,
                t.format("DD_MM_YYYY_HH_mm_ss"),
            )
            curtailment_bid_name = self.CURTAILMENT_ORDER_NAME_TEMPLATE.format(
                parameters.temporal.execution_date.format("DD_MM_YYYY_HH_mm_ss"),
                equipment.name,
                t.format("DD_MM_YYYY_HH_mm_ss"),
            )

            if abs(curtailment_value) >= parameters.allowed_round_off_error:
                if curtailment_value < 0:
                    # curtailment_delta < 0: curtailment margin available → sell (reduce production at price 0)
                    curtailment_bid = build_intraday_order(
                        equipment, curtailment_bid_name, 0.0, 0.0, abs(curtailment_value), OrderType.Sell, t, parameters
                    )
                    orders.append(curtailment_bid)
                    sell_values[i] += abs(curtailment_value)
                else:
                    # curtailment_delta > 0: over-curtailed → buy back the committed volume
                    curtailment_bid = build_intraday_order(
                        equipment, curtailment_bid_name, 0.0, 0.0, abs(curtailment_value), OrderType.Buy, t, parameters
                    )
                    orders.append(curtailment_bid)
                    buy_values[i] += abs(curtailment_value)

            if abs(production_value) <= parameters.allowed_round_off_error:
                continue

            if production_value > 0:
                bid = build_intraday_order(
                    equipment,
                    bid_name,
                    variable_costs.get_value(t),
                    0.0,
                    abs(production_value),
                    OrderType.Sell,
                    t,
                    parameters,
                )
                orders.append(bid)
                sell_values[i] += abs(production_value)

            if production_value < 0:
                bid = build_intraday_order(
                    equipment,
                    bid_name,
                    variable_costs.get_value(t) + imbalance_penalty_price,
                    0.0,
                    abs(production_value),
                    OrderType.Buy,
                    t,
                    parameters,
                )
                orders.append(bid)
                buy_values[i] += abs(production_value)

        sell_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, sell_values
        )
        buy_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, buy_values
        )
        return orders, [], sell_submitted_volume, buy_submitted_volume
