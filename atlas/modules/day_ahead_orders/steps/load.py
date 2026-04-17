"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.enums import LoadType, OrderType, Product
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractOrderStep, StepResult


class LoadStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
        result = StepResult()

        for load in self.dataset.load:
            if load.maximum_power_forecast is None:
                cfg.logger.warning(f"maximum_power_forecast is None for load {load.name}, {load.load_type}")
            else:
                consumption_forecast = load.maximum_power_forecast.get_forecast(
                    self.parameters.temporal.execution_date,
                    self.parameters.temporal.start_date,
                    self.parameters.penultimate_date,
                    self.parameters.temporal.timestep,
                )

                if load.da_buy_submitted_volume is None:
                    load.da_buy_submitted_volume = Timeseries(consumption_forecast.abs())
                else:
                    load.da_buy_submitted_volume += consumption_forecast.abs()

                if len(consumption_forecast) == 0:
                    cfg.logger.debug(f"consumption_forecast is empty for load {load.name}, {load.load_type}")
                else:
                    for t in self.orders_time:
                        max_consumption_value = abs(consumption_forecast.get_value(t))

                        if max_consumption_value > 0:
                            result.orders.append(
                                OrderDAO(
                                    name=f"load_order_at_{t}_for_unit_{load.name}",
                                    market_area=load.portfolio.market_area,
                                    portfolio=load.portfolio,
                                    equipment=load,
                                    qmax=max_consumption_value,
                                    qmin=0,
                                    product=Product.DayAhead,
                                    order_type=OrderType.Buy,
                                    is_agent_tso=False,
                                    execution_date=self.parameters.temporal.execution_date,
                                    start_date=t,
                                    end_date=t + self.parameters.temporal.timestep,
                                    price=load.variable_cost.get_value(t)
                                    if load.load_type == LoadType.POWER_TO_GAS
                                    else self.parameters.load_price,
                                )
                            )

        return result
