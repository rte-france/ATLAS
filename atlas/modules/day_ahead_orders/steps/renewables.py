"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.enums import OrderType, Product
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.wind import WindDAO
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractOrderStep, StepResult


class WindPVStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
        result = StepResult()
        equipments_list = self.dataset.wind + self.dataset.solar

        for equipment in equipments_list:
            if equipment.maximum_power_forecast is None:
                cfg.logger.warning(f"maximum_power_forecast is None for wind/photovoltaic {equipment.name}")
            else:
                production_forecast = equipment.maximum_power_forecast.get_forecast(
                    self.parameters.temporal.execution_date,
                    self.parameters.temporal.start_date,
                    self.parameters.penultimate_date,
                )
                if equipment.da_sell_submitted_volume is None:
                    equipment.da_sell_submitted_volume = production_forecast
                else:
                    equipment.da_sell_submitted_volume += production_forecast

                for t in self.orders_time:
                    if isinstance(equipment, WindDAO):
                        bid_name = f"wind_order_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{equipment.name}_exec_{self.parameters.temporal.execution_date.hour}"
                    else:
                        bid_name = f"pv_order_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{equipment.name}_exec_{self.parameters.temporal.execution_date.hour}"

                    max_production_value = production_forecast.get_value(t)
                    min_production_value = max_production_value * (1 - equipment.maximum_curtailment_ratio.get_value(t))

                    if max_production_value > 0:
                        result.orders.append(
                            OrderDAO(
                                name=bid_name,
                                market_area=equipment.portfolio.market_area,
                                portfolio=equipment.portfolio,
                                equipment=equipment,
                                qmax=max_production_value,
                                qmin=min_production_value,
                                price=0.0 if equipment.variable_cost is None else equipment.variable_cost.get_value(t),
                                product=Product.DayAhead,
                                order_type=OrderType.Sell,
                                is_agent_tso=False,
                                execution_date=self.parameters.temporal.execution_date,
                                start_date=t,  # type: ignore [arg-type]
                                end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                            )
                        )

        return result
