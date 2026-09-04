"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.enums import OrderType, Product
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractOrderStep, StepResult


class NonDispatchableStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
        result = StepResult()

        for unit in self.dataset.other_non_dispatchable:
            if unit.maximum_power_forecast is None:
                cfg.logger.warning(f"maximum_power_forecast is None for other_non_dispatchable {unit.name}")
            else:
                sell_submitted_volume = unit.maximum_power_forecast.get_forecast(
                    self.parameters.temporal.execution_date,
                    self.parameters.temporal.start_date,
                    self.parameters.penultimate_date,
                    self.parameters.temporal.timestep,
                )

                if unit.da_sell_submitted_volume is None:
                    unit.da_sell_submitted_volume = sell_submitted_volume
                else:
                    unit.da_sell_submitted_volume = unit.da_sell_submitted_volume.add_on_union(
                        sell_submitted_volume, inplace=False
                    )

                for t in self.orders_time:
                    result.orders.append(
                        OrderDAO(
                            name=f"other_nd_order_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}",
                            market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
                            portfolio=unit.portfolio,
                            equipment=unit,
                            qmax=sell_submitted_volume.get_value(t),
                            qmin=0,
                            price=0.0 if unit.variable_cost is None else unit.variable_cost.get_value(t),
                            product=Product.DayAhead,
                            order_type=OrderType.Sell,
                            is_agent_tso=False,
                            execution_date=self.parameters.temporal.execution_date,
                            start_date=t,  # type: ignore [arg-type]
                            end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                        )
                    )

        return result
