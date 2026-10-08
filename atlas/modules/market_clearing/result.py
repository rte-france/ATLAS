"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from enum import Enum, auto
from typing import Any

import atlas.config as cfg
from atlas.abstract_class.dataset import ModuleResult
from atlas.enums import Product
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.data_classes import ClearingOutputs
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.parameters import ExchangeConstraintsType, MarketClearingParameters
from atlas.objects.equipment.equipment import Equipment
from atlas.objects.market.critical_branch import CriticalBranch
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market.market_border import MarketBorder
from atlas.objects.market.order import Order
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.orchestrator.change_set import ChangeSet, UpdateObject


class Merge(Enum):
    """How the values cleared over the horizon are merged into an attribute."""

    APPEND = auto()  # timeseries history, followed by the window
    CUMULATE = auto()  # timeseries total over the successive clearings
    FORECAST = auto()  # forecasting matrix, the window indexed by the execution date


APPEND, CUMULATE, FORECAST = Merge.APPEND, Merge.CUMULATE, Merge.FORECAST

# Attributes updated for each market, by object and by cleared series
type Fields = dict[Product, dict[str, Merge]]

EQUIPMENT_FIELDS: Fields = {
    Product.DayAhead: {"da_cleared_quantity": APPEND},
    Product.Intraday: {"total_id_cleared_quantity": CUMULATE, "id_cleared_quantity": FORECAST},
    Product.AFRRUpProcurement: {"afrr_up_procured": FORECAST},
    Product.AFRRDownProcurement: {"afrr_down_procured": FORECAST},
    Product.MFRRUpProcurement: {"mfrr_up_procured": FORECAST},
    Product.MFRRDownProcurement: {"mfrr_down_procured": FORECAST},
    Product.RRUpProcurement: {"rr_up_procured": FORECAST},
    Product.RRDownProcurement: {"rr_down_procured": FORECAST},
    Product.AFRRActivation: {"afrr_activated": APPEND},
    Product.MFRRActivation: {"mfrr_activated": APPEND},
    Product.RRActivation: {"rr_activated": APPEND},
    Product.FCRActivation: {"fcr_activated": APPEND},
}
PORTFOLIO_FIELDS: Fields = {
    Product.DayAhead: {"da_cleared_quantity": APPEND},
    Product.Intraday: {"total_id_cleared_quantity": CUMULATE, "id_cleared_quantity": FORECAST},
    Product.AFRRUpProcurement: {"afrr_up_procured": APPEND},
    Product.AFRRDownProcurement: {"afrr_down_procured": APPEND},
    Product.MFRRUpProcurement: {"mfrr_up_procured": APPEND},
    Product.MFRRDownProcurement: {"mfrr_down_procured": APPEND},
    Product.RRUpProcurement: {"rr_up_procured": APPEND},
    Product.RRDownProcurement: {"rr_down_procured": APPEND},
    Product.AFRRActivation: {"afrr_activated": APPEND},
    Product.MFRRActivation: {"mfrr_activated": APPEND},
    Product.RRActivation: {"rr_activated": APPEND},
    Product.FCRActivation: {"fcr_activated": APPEND},
}
MARKET_AREA_PRICE_FIELDS: Fields = {
    Product.DayAhead: {"da_price": APPEND},
    Product.Intraday: {"id_price": FORECAST},
    Product.AFRRActivation: {"afrr_activation_price": APPEND},
    Product.MFRRActivation: {"mfrr_activation_price": APPEND},
    Product.RRActivation: {"rr_activation_price": APPEND},
    Product.FCRActivation: {"fcr_activation_price": APPEND},
}
MARKET_AREA_BALANCE_FIELDS: Fields = {
    Product.DayAhead: {"da_balance": APPEND},
    Product.Intraday: {"total_id_balance": CUMULATE, "id_balance": FORECAST},
    Product.MFRRActivation: {"mfrr_activation_balance": APPEND},
    Product.RRActivation: {"rr_activation_balance": APPEND},
}
MARKET_BORDER_FLOW_FIELDS: Fields = {
    Product.DayAhead: {"da_flow": APPEND},
    Product.Intraday: {"total_id_flow": APPEND, "id_flow": FORECAST},
    Product.AFRRUpProcurement: {"afrr_up_procured": FORECAST},
    Product.AFRRDownProcurement: {"afrr_down_procured": FORECAST},
    Product.MFRRUpProcurement: {"mfrr_up_procured": FORECAST},
    Product.MFRRDownProcurement: {"mfrr_down_procured": FORECAST},
    Product.RRUpProcurement: {"rr_up_procured": FORECAST},
    Product.RRDownProcurement: {"rr_down_procured": FORECAST},
    Product.AFRRActivation: {"afrr_activated": APPEND},
    Product.MFRRActivation: {"mfrr_activated": APPEND},
    Product.RRActivation: {"rr_activated": APPEND},
    Product.FCRActivation: {"fcr_activated": APPEND},
}
MARKET_BORDER_SHADOW_PRICE_FIELDS: Fields = {
    Product.DayAhead: {"da_shadow_price": APPEND},
    Product.Intraday: {"id_shadow_price": FORECAST},
}
CRITICAL_BRANCH_FLOW_FIELDS: Fields = {
    Product.DayAhead: {"da_flow": APPEND},
    Product.Intraday: {"total_id_flow": CUMULATE, "id_flow": FORECAST},
}


class MarketClearingResult(ModuleResult[MarketClearingParameters]):
    """Output dataset for Market Clearing module"""

    def __init__(
        self,
        input_dataset: MarketClearingInputDataset,
        clearing_outputs: ClearingOutputs,
        market_prices: dict[str, Timeseries],
    ):
        self.input_dataset = input_dataset
        self.accepted_powers = clearing_outputs.accepted_powers
        self.local_balances = clearing_outputs.local_balances
        self.border_exchanges = clearing_outputs.border_exchanges
        self.market_prices = market_prices

    def build_change_sets(self) -> list[ChangeSet]:
        change_sets = self.update_orders() + self.update_market_area() + self.update_market_border()
        if self.input_dataset.parameters.exchange_constraints_type == ExchangeConstraintsType.FB:
            change_sets += self.update_critical_branches()
        return change_sets

    def update_orders(self) -> list[ChangeSet]:
        change_sets: list[ChangeSet] = []
        times = self.input_dataset.times
        timestep = self.input_dataset.parameters.temporal.timestep
        position = {time: index for index, time in enumerate(times)}
        # Power sold by each equipment and portfolio at each timestep, summed as plain lists and turned into
        # timeseries once: a timeseries operation per order is far too slow
        equipments_sold: dict[str, tuple[Equipment, list[float]]] = {}
        portfolios_sold: dict[str, tuple[Portfolio, list[float]]] = {}

        if self.input_dataset.parameters.market == Product.DayAhead:
            for equipment in self.input_dataset.input_data.iter_by_equipments():
                portfolio = equipment.portfolio
                if portfolio is None or portfolio.market_area is None:
                    continue
                if portfolio.market_area.name not in self.input_dataset.market_areas:
                    continue
                equipments_sold[equipment.name] = (equipment, [0.0] * len(times))
                portfolios_sold.setdefault(portfolio.name, (portfolio, [0.0] * len(times)))

        for order_name, order in self.input_dataset.orders.items():
            accepted_power = self.accepted_powers[order.market_area.name, order_name]
            # At this point, unaccepted orders can be skipped:
            if abs(accepted_power) <= self.input_dataset.parameters.allowed_round_off_error:
                continue
            # The surplus of an order is the gain made by its emitter computed from the present spot price:
            spot_price = self.market_prices[order.market_area.name].get_value(order.start_date)
            individual_spread = spot_price - order.price if order.is_sale else order.price - spot_price
            updated_values = {
                "name": order_name,
                "accepted_power": accepted_power,
                "individual_spread": individual_spread,
            }
            change_sets.append(UpdateObject(updated_values, Order))

            order_equipment = order.equipment
            if order.is_agent_tso or order_equipment is None or order_equipment.portfolio is None:
                continue
            portfolio = order_equipment.portfolio
            _, equipment_sold = equipments_sold.setdefault(order_equipment.name, (order_equipment, [0.0] * len(times)))
            _, portfolio_sold = portfolios_sold.setdefault(portfolio.name, (portfolio, [0.0] * len(times)))
            power_sold = accepted_power * order.production_sign
            for index in range(position[order.start_date], position[order.end_date_processed - timestep] + 1):
                equipment_sold[index] += power_sold
                portfolio_sold[index] += power_sold

        for equipment_name, (equipment, values) in equipments_sold.items():
            updated_values = {
                "name": equipment_name,
                **self.merged(equipment, EQUIPMENT_FIELDS, self.horizon_timeseries(values)),
            }
            change_sets.append(UpdateObject(updated_values, type(equipment)))

        for portfolio_name, (portfolio, values) in portfolios_sold.items():
            updated_values = {
                "name": portfolio_name,
                **self.merged(portfolio, PORTFOLIO_FIELDS, self.horizon_timeseries(values)),
            }
            change_sets.append(UpdateObject(updated_values, Portfolio))
        return change_sets

    def update_market_area(self) -> list[ChangeSet]:
        change_sets: list[ChangeSet] = []
        for market_area_name, market_area in self.input_dataset.market_areas.items():
            updated_values = {
                "name": market_area_name,
                **self.merged(market_area, MARKET_AREA_PRICE_FIELDS, self.market_prices[market_area_name]),
                **self.merged(market_area, MARKET_AREA_BALANCE_FIELDS, self.local_balances[market_area_name]),
            }
            change_sets.append(UpdateObject(updated_values, MarketArea))
        return change_sets

    def update_market_border(self) -> list[ChangeSet]:
        change_sets: list[ChangeSet] = []
        for market_border_name, market_border in self.input_dataset.market_borders.items():
            flow = self.border_exchanges[market_border_name]
            shadow_price = (
                self.market_prices[market_border.uphill_market_area.name]
                - self.market_prices[market_border.downhill_market_area.name]
            )
            updated_values = {
                "name": market_border_name,
                **self.merged(market_border, MARKET_BORDER_FLOW_FIELDS, flow),
                **self.merged(market_border, MARKET_BORDER_SHADOW_PRICE_FIELDS, shadow_price),
                # Update ReferenceFlow, otherwise the flow can be out of bounds for future markets
                "reference_flow": self.merge(market_border.reference_flow, flow, Merge.CUMULATE),
            }
            # Remark : Flow markets are not yet taken into account.
            change_sets.append(UpdateObject(updated_values, MarketBorder))
        return change_sets

    def update_critical_branches(self) -> list[ChangeSet]:
        change_sets: list[ChangeSet] = []
        relative_balances = {}
        for market_area_name, market_area in self.input_dataset.market_areas.items():
            for time in self.input_dataset.times:
                relative_balances[market_area_name, time] = self.local_balances[market_area_name].get_value(
                    time
                ) - market_area.ref_balance.get_value(time)

        for critical_branch in self.input_dataset.critical_branches.values():
            updated_values = {"name": critical_branch.name}
            flow = self.horizon_timeseries([0.0] * len(self.input_dataset.times))
            for market_area_ptdf in critical_branch.market_area_ptdf:
                da_ptdf = market_area_ptdf.da_ptdf.set_frequency(
                    self.input_dataset.parameters.temporal.timestep, False
                ).filter(self.input_dataset.times)  # type: ignore[arg-type]
                flow += da_ptdf

            if self.input_dataset.parameters.market not in CRITICAL_BRANCH_FLOW_FIELDS:
                cfg.logger.info(
                    "ATLAS 1.3 does not support exports on critical branches for this market. "
                    "This should be corrected in future versions"
                )
            updated_values |= self.merged(critical_branch, CRITICAL_BRANCH_FLOW_FIELDS, flow)
            change_sets.append(UpdateObject(updated_values, CriticalBranch))
        return change_sets

    def merged(self, obj: Any, fields: Fields, window: Timeseries) -> dict[str, Any]:
        """
        Merge the window cleared over the horizon into each attribute of *obj* updated by the market.

        :param obj: Object holding the attributes
        :type obj: Any
        :param fields: Attributes updated for each market, and how they are merged
        :type fields: Fields
        :param window: Values cleared over the horizon
        :type window: Timeseries
        :return: The new value of each attribute updated by the market
        :rtype: dict[str, Any]
        """
        return {
            attribute: self.merge(getattr(obj, attribute), window, how)
            for attribute, how in fields.get(self.input_dataset.parameters.market, {}).items()
        }

    def merge(self, history: Any, window: Timeseries, how: Merge) -> Any:
        """
        Merge the window cleared over the horizon into the current value of an attribute.

        A timeseries history of less than two timesteps has no frequency to check the window
        against: it is replaced by the window.

        :param history: Current value of the attribute, a timeseries or a forecasting matrix
        :type history: AbstractTimeseries | ForecastingMatrix | LazyForecastingMatrix | None
        :param window: Values cleared over the horizon
        :type window: Timeseries
        :param how: How the window is merged
        :type how: Merge
        :return: The new value of the attribute
        :rtype: AbstractTimeseries | ForecastingMatrix | LazyForecastingMatrix
        :raises ValueError: If the window leaves a gap after the history, or overlaps it when appended
        """
        if how == Merge.FORECAST:
            forecast = ForecastingMatrix() if history is None else history
            return forecast.add(window, self.input_dataset.parameters.temporal.execution_date)
        if history is None or len(history) < 2:
            return window
        if how == Merge.APPEND:
            return history.add_indexes(window, inplace=False)
        return history.add_on_union(window, inplace=False)

    def horizon_timeseries(self, values: list[float]) -> Timeseries:
        """
        Build a Timeseries over the clearing horizon.

        :param values: One value per timestep of the clearing
        :type values: list[float]
        :return: The values indexed by the timesteps of the clearing
        :rtype: Timeseries
        """
        times = self.input_dataset.times
        return Timeseries({"time": times, "value": values}, timezone=times[0].timezone_name or "UTC")
