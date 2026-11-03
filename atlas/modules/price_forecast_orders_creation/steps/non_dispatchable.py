"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.enums import OrderType
from atlas.modules.price_forecast_orders_creation.steps.abstract_step import AbstractOrderStep, StepResult


class NonDispatchableStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
        result = StepResult()
        for equipment in self.dataset.other_non_dispatchable:
            local_power = equipment.maximum_power_forecast.get_forecast(
                self.parameters.default_exec_date,
                self.parameters.start_date,
                self.parameters.end_date.AddMinutes(-self.parameters.time_step),
            )

            for time in self.orders_time:
                if local_power.get_value(time) < 0:
                    order_type = OrderType.Buy
                    price_ond = 3000
                else:
                    order_type = OrderType.Sell
                    price_ond = -500

                qmax = abs(local_power.get_value(time))

                result.orders.append(self.create_order(time, equipment, order_type, price_ond, qmax, qmax, False))
        return result
