"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import statistics
from collections.abc import Iterator

import atlas.config as cfg
from atlas import generate_datetimes
from atlas.enums import OrderType
from atlas.modules.price_forecast_orders_creation.input_objects.order import OrderPFOC
from atlas.modules.price_forecast_orders_creation.input_objects.storage import StoragePFOC
from atlas.modules.price_forecast_orders_creation.parameters import StoragePriceMethodType
from atlas.modules.price_forecast_orders_creation.steps.abstract_step import AbstractOrderStep, StepResult


class StorageStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
        """
        To imitate the formulation of storage units done by the DAO, both the volumes
        (and their temporal placement) and prices of offers have to be determined.
        The placement of volumes is a direct output of the Antares dispatch.
        Prices are harder to determine. The marginal price in each area is taken
        into account (typically given by PriceForecastMedium).
        """
        result = StepResult()

        if self.parameters.storage_price_method == StoragePriceMethodType.precompute:
            for equipment in self.dataset.storage:
                result.orders.extend(self._orders(equipment, True))
        else:
            for equipment in self.dataset.storage:
                min_sell, max_buy = self._reference_prices(equipment)
                sell, buy = self._final_prices(equipment, min_sell, max_buy)
                result.orders.extend(self._orders(equipment, False, sell, buy))
        return result

    def _reference_prices(self, equipment: StoragePFOC) -> tuple[float, float]:
        """Min sell / max buy reference prices over the extended optimization horizon."""
        additional_hours = (
            equipment.additional_hours.day_ahead
        )  # FIXME-1 shouldn't the additional_hours be based on self.parameter.market? see others FIXME-1
        complete_orders_time = generate_datetimes(
            self.parameters.temporal.start_date,
            self.parameters.penultimate_date + additional_hours,
            self.parameters.temporal.timestep,
        )
        price_forecast = equipment.portfolio.market_area.price_forecast_medium.get_forecast(
            self.parameters.default_exec_date,
            self.parameters.temporal.start_date,
            self.parameters.penultimate_date + additional_hours,
            self.parameters.temporal.timestep,
        )

        sell_prices: list[float] = []
        buy_prices: list[float] = []
        for time in complete_orders_time:
            dispatch = equipment.antares_dispatch.get_value(time)
            if dispatch > 0:
                sell_prices.append(price_forecast.get_value(time))
            elif dispatch < 0:
                buy_prices.append(price_forecast.get_value(time))

        cap = self.parameters.market_price_cap
        if self.parameters.storage_price_method == StoragePriceMethodType.median:
            min_sell = statistics.median(sell_prices) if sell_prices else cap
            max_buy = statistics.median(buy_prices) if buy_prices else 0.0
        else:  # StoragePriceMethodType == standard | buy_unbounded
            min_sell = min([cap, *sell_prices])
            max_buy = max([0.0, *buy_prices])
        return min_sell, max_buy

    def _final_prices(self, equipment: StoragePFOC, min_sell: float, max_buy: float) -> tuple[float, float]:
        """Applies the efficiency-based spread between sell and buy prices."""
        if min_sell < max_buy:
            cfg.logger.warning(
                f"Formulation of the {self.parameters.market} orders, "
                f"Storage {equipment.name} at {self.parameters.temporal.execution_date}: "
                f"sell price ({min_sell}) lower than the buy price ({max_buy}), "
                "which may lead to weird behaviors in the Clearing process. "
                "Sell price has been set to buy price."
            )
            min_sell = max_buy

        if min_sell == 0 and max_buy == 0:
            return 0.0, 0.0

        efficiency = equipment.charge_efficiency * equipment.discharge_efficiency
        numerator = efficiency * min_sell - max_buy
        denominator = efficiency * min_sell + max_buy
        if denominator != 0:
            a = max(0.0, min(numerator / denominator, 1.0))
        else:
            a = 0.0  # FIXME - this case wasn't handle in prometheus

        final_sell_price = min_sell * (1 - a)
        if self.parameters.storage_price_method == StoragePriceMethodType.buy_unbounded:
            final_buy_price = max_buy
        else:  # StoragePriceMethodType == standard | median
            final_buy_price = max_buy * (1 + a)
        return final_sell_price, final_buy_price

    def _orders(
        self, equipment: StoragePFOC, variable_price: bool = True, sell_price: float = 0.0, buy_price: float = 0.0
    ) -> Iterator[OrderPFOC]:
        """One order per timestep with non-zero dispatch: Sell if > 0, Buy if < 0."""
        for time in self.orders_time:
            dispatch = equipment.antares_dispatch.get_value(time)
            if dispatch == 0:
                continue
            direction = OrderType.Sell if dispatch > 0 else OrderType.Buy
            if variable_price:
                price = equipment.variable_cost.get_value(time)
            else:
                price = sell_price if dispatch > 0 else buy_price

            order = self.create_order(
                time=time,
                equipment=equipment,
                order_type=direction,
                price=price,
                qmin=0,
                qmax=abs(dispatch),
                is_agent_tso=False,
            )
            if order is not None:  # create_order returns None when rounded qmax <= 0
                yield order
