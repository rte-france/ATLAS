"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from itertools import chain
from atlas.enums import OrderType
from atlas.modules.price_forecast_orders_creation.steps.abstract_step import AbstractOrderStep, StepResult


class WindAndSolarStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
        result = StepResult()
        for equipment in chain(self.dataset.wind, self.dataset.solar):
            local_power = equipment.maximum_power_forecast.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.penultimate_date
            )

            # Now we loop over the time stamps for which we want an offer to be made.
            # We formulate as many offers as there are time stamps in time_index.
            for time in self.orders_time:
                order = self.create_order(
                    time=time,
                    equipment=equipment,
                    order_type=OrderType.Sell,
                    price=equipment.variable_cost.get_value(time),
                    qmin=0,
                    qmax=local_power.get_value(time),
                    is_agent_tso=False,
                )
                if order is not None:
                    result.orders.append(order)
        return result