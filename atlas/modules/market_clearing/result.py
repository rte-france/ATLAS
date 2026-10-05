"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

import atlas.config as cfg
from atlas.abstract_class.dataset import ModuleResult
from atlas.enums import Product
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
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


class MarketClearingResult(ModuleResult[MarketClearingParameters]):
    """Output dataset for Market Clearing module
    What to we need from MarketClearing result :
      - accepted_powers
      - local_balances
      - border_exchanges
      - market_prices

    Updated values are :
    - MarketArea :
      - DABalance
      - DAPrice
      - TotalIDBalance
      - IDBalance
      - IDPrice
      - RRActivationPrice
      - RRActivationBalance
      - MFRRActivationPrice
      - MFRRActivationBalance
      - AFRRActivationPrice
      - FCRActivationPrice
    - MarketBorder :
      - DAFlow
      - DAShadowPrice
      - TotalIDFlow
      - IDFlow
      - IDShadowPrice
      - MFRRUpProcurement
      - MFRRDownProcurement
      - AFRRUpProcurement
      - AFRRDownProcurement
      - RRUpProcurement
      - RRDownProcurement
      - RRActivated
      - MFRRActivated
      - AFRRActivated
      - FCRActivated
      - ReferenceFlow
    - CriticalBranch :
      - DAFlow
      - DAShadowPrice
      - TotalIDFlow
      - IDFlow
      - IDShadowPrice
      - MFRRUpProcurement
      - MFRRDownProcurement
      - AFRRUpProcurement
      - AFRRDownProcurement
      - RRUpProcurement
      - RRDownProcurement
      - RRActivated
      - MFRRActivated
      - AFRRActivated
      - FCRActivated
      - ReferenceFlow
    - Order :
      - accepted_power
      - IndividualSpread
    - Equipment :
      - DAClearedQuantity
      - TotalIDClearedQuantity
      - IDClearedQuantity
      - AFRRUpProcured
      - AFRRDownProcured
      - MFRRUpProcured
      - MFRRDownProcured
      - RRUpProcured
      - RRDownProcured
      - RRActivated
      - MFRRActivated
      - AFRRActivated
      - FCRActivated
    - Portfolio :
      - DAClearedQuantity
      - AFRRUpProcured
      - AFRRDownProcured
      - MFRRUpProcured
      - MFRRDownProcured
      - RRUpProcured
      - RRDownProcured
      - RRActivated
      - MFRRActivated
      - AFRRActivated
      - FCRActivated

    """

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
            updated_values: dict[str, Any] = {
                "name": order_name,
                "accepted_power": accepted_power,
                "individual_spread": individual_spread,
            }
            change_sets.append(UpdateObject(updated_values, Order))

            equipment = order.equipment
            if order.is_agent_tso or equipment is None or equipment.portfolio is None:
                continue
            portfolio = equipment.portfolio
            _, equipment_sold = equipments_sold.setdefault(equipment.name, (equipment, [0.0] * len(times)))
            _, portfolio_sold = portfolios_sold.setdefault(portfolio.name, (portfolio, [0.0] * len(times)))
            power_sold = accepted_power * order.production_sign
            for index in range(position[order.start_date], position[order.end_date_processed - timestep] + 1):
                equipment_sold[index] += power_sold
                portfolio_sold[index] += power_sold

        for equipment_name, (equipment, values) in equipments_sold.items():
            equipment_ts = self.horizon_timeseries(values)
            updated_values: dict[str, Any] = {"name": equipment_name}
            match self.input_dataset.parameters.market:
                case Product.DayAhead:
                    updated_values["da_cleared_quantity"] = self.add_indexes(
                        equipment.da_cleared_quantity, equipment_ts
                    )
                case Product.AFRRUpProcurement:
                    updated_values["afrr_up_procured"] = self.add_timeseries_to_forecast(
                        equipment.afrr_up_procured, equipment_ts
                    )
                case Product.AFRRDownProcurement:
                    updated_values["afrr_down_procured"] = self.add_timeseries_to_forecast(
                        equipment.afrr_down_procured, equipment_ts
                    )
                case Product.MFRRUpProcurement:
                    updated_values["mfrr_up_procured"] = self.add_timeseries_to_forecast(
                        equipment.mfrr_up_procured, equipment_ts
                    )
                case Product.MFRRDownProcurement:
                    updated_values["mfrr_down_procured"] = self.add_timeseries_to_forecast(
                        equipment.mfrr_down_procured, equipment_ts
                    )
                case Product.RRUpProcurement:
                    updated_values["rr_up_procured"] = self.add_timeseries_to_forecast(
                        equipment.rr_up_procured, equipment_ts
                    )
                case Product.RRDownProcurement:
                    updated_values["rr_down_procured"] = self.add_timeseries_to_forecast(
                        equipment.rr_down_procured, equipment_ts
                    )
                case Product.AFRRActivation:
                    updated_values["afrr_activated"] = self.add_indexes(equipment.afrr_activated, equipment_ts)
                case Product.MFRRActivation:
                    updated_values["mfrr_activated"] = self.add_indexes(equipment.mfrr_activated, equipment_ts)
                case Product.RRActivation:
                    updated_values["rr_activated"] = self.add_indexes(equipment.rr_activated, equipment_ts)
                case Product.FCRActivation:
                    updated_values["fcr_activated"] = self.add_indexes(equipment.fcr_activated, equipment_ts)
                case Product.Intraday:
                    updated_values["total_id_cleared_quantity"] = self.add_indexes_or_sum(
                        equipment.total_id_cleared_quantity, equipment_ts
                    )
                    updated_values["id_cleared_quantity"] = self.add_timeseries_to_forecast(
                        equipment.id_cleared_quantity, equipment_ts
                    )
            # Update the Equipment
            change_sets.append(UpdateObject(updated_values, type(equipment)))

        for portfolio_name, (portfolio, values) in portfolios_sold.items():
            portfolio_ts = self.horizon_timeseries(values)
            updated_values: dict[str, Any] = {"name": portfolio_name}
            match self.input_dataset.parameters.market:
                case Product.DayAhead:
                    updated_values["da_cleared_quantity"] = self.add_indexes(
                        portfolio.da_cleared_quantity, portfolio_ts
                    )
                case Product.AFRRUpProcurement:
                    updated_values["afrr_up_procured"] = self.add_indexes(portfolio.afrr_up_procured, portfolio_ts)
                case Product.AFRRDownProcurement:
                    updated_values["afrr_down_procured"] = self.add_indexes(portfolio.afrr_down_procured, portfolio_ts)
                case Product.MFRRUpProcurement:
                    updated_values["mfrr_up_procured"] = self.add_indexes(portfolio.mfrr_up_procured, portfolio_ts)
                case Product.MFRRDownProcurement:
                    updated_values["mfrr_down_procured"] = self.add_indexes(portfolio.mfrr_down_procured, portfolio_ts)
                case Product.RRUpProcurement:
                    updated_values["rr_up_procured"] = self.add_indexes(portfolio.rr_up_procured, portfolio_ts)
                case Product.RRDownProcurement:
                    updated_values["rr_down_procured"] = self.add_indexes(portfolio.rr_down_procured, portfolio_ts)
                case Product.AFRRActivation:
                    updated_values["afrr_activated"] = self.add_indexes(portfolio.afrr_activated, portfolio_ts)
                case Product.MFRRActivation:
                    updated_values["mfrr_activated"] = self.add_indexes(portfolio.mfrr_activated, portfolio_ts)
                case Product.RRActivation:
                    updated_values["rr_activated"] = self.add_indexes(portfolio.rr_activated, portfolio_ts)
                case Product.FCRActivation:
                    updated_values["fcr_activated"] = self.add_indexes(portfolio.fcr_activated, portfolio_ts)
                case Product.Intraday:
                    updated_values["total_id_cleared_quantity"] = self.add_indexes_or_sum(
                        portfolio.total_id_cleared_quantity, portfolio_ts
                    )
                    updated_values["id_cleared_quantity"] = self.add_timeseries_to_forecast(
                        portfolio.id_cleared_quantity, portfolio_ts
                    )
            # Update the Portfolio
            change_sets.append(UpdateObject(updated_values, Portfolio))
        return change_sets

    def update_market_area(self) -> list[ChangeSet]:
        change_sets: list[ChangeSet] = []
        for market_area_name, market_area in self.input_dataset.market_areas.items():
            updated_values: dict[str, Any] = {"name": market_area_name}
            values_bal = self.local_balances[market_area_name]
            values_price = self.market_prices[market_area_name]

            match self.input_dataset.parameters.market:
                case Product.DayAhead:
                    updated_values["da_price"] = self.add_indexes(market_area.da_price, values_price)
                    updated_values["da_balance"] = self.add_indexes(market_area.da_balance, values_bal)
                case Product.Intraday:
                    updated_values["total_id_balance"] = self.add_indexes_or_sum(
                        market_area.total_id_balance, values_bal
                    )
                    updated_values["id_price"] = self.add_timeseries_to_forecast(market_area.id_price, values_price)
                    updated_values["id_balance"] = self.add_timeseries_to_forecast(market_area.id_balance, values_bal)
                case Product.RRActivation:
                    updated_values["rr_activation_price"] = self.add_indexes(
                        market_area.rr_activation_price, values_price
                    )
                    updated_values["rr_activation_balance"] = self.add_indexes(
                        market_area.rr_activation_balance, values_bal
                    )
                case Product.MFRRActivation:
                    updated_values["mfrr_activation_price"] = self.add_indexes(
                        market_area.mfrr_activation_price, values_price
                    )
                    updated_values["mfrr_activation_balance"] = self.add_indexes(
                        market_area.mfrr_activation_balance, values_bal
                    )
                case Product.AFRRActivation:
                    updated_values["afrr_activation_price"] = self.add_indexes(
                        market_area.afrr_activation_price, values_price
                    )
                case Product.FCRActivation:
                    updated_values["fcr_activation_price"] = self.add_indexes(
                        market_area.fcr_activation_price, values_price
                    )

            # Update the Market Area
            change_sets.append(UpdateObject(updated_values, MarketArea))
        return change_sets

    def update_market_border(self) -> list[ChangeSet]:
        change_sets: list[ChangeSet] = []
        for market_border_name, market_border in self.input_dataset.market_borders.items():
            updated_values: dict[str, Any] = {"name": market_border_name}
            flow = self.border_exchanges[market_border_name]
            shadow_price = (
                self.market_prices[market_border.uphill_market_area.name]
                - self.market_prices[market_border.downhill_market_area.name]
            )
            match self.input_dataset.parameters.market:
                case Product.DayAhead:
                    updated_values["da_flow"] = self.add_indexes(market_border.da_flow, flow)
                    updated_values["da_shadow_price"] = self.add_indexes(market_border.da_shadow_price, shadow_price)
                case Product.Intraday:
                    updated_values["total_id_flow"] = self.add_indexes(market_border.total_id_flow, flow)
                    updated_values["id_flow"] = self.add_timeseries_to_forecast(market_border.id_flow, flow)
                    updated_values["id_shadow_price"] = self.add_timeseries_to_forecast(
                        market_border.id_shadow_price, shadow_price
                    )
                case Product.MFRRUpProcurement:
                    updated_values["mfrr_up_procured"] = self.add_timeseries_to_forecast(
                        market_border.mfrr_up_procured, flow
                    )
                case Product.MFRRDownProcurement:
                    updated_values["mfrr_down_procured"] = self.add_timeseries_to_forecast(
                        market_border.mfrr_down_procured, flow
                    )
                case Product.AFRRUpProcurement:
                    updated_values["afrr_up_procured"] = self.add_timeseries_to_forecast(
                        market_border.afrr_up_procured, flow
                    )
                case Product.AFRRDownProcurement:
                    updated_values["afrr_down_procured"] = self.add_timeseries_to_forecast(
                        market_border.afrr_down_procured, flow
                    )
                case Product.RRUpProcurement:
                    updated_values["rr_up_procured"] = self.add_timeseries_to_forecast(
                        market_border.rr_up_procured, flow
                    )
                case Product.RRDownProcurement:
                    updated_values["rr_down_procured"] = self.add_timeseries_to_forecast(
                        market_border.rr_down_procured, flow
                    )
                case Product.RRActivation:
                    updated_values["rr_activated"] = self.add_indexes(market_border.rr_activated, flow)
                case Product.MFRRActivation:
                    updated_values["mfrr_activated"] = self.add_indexes(market_border.mfrr_activated, flow)
                case Product.AFRRActivation:
                    updated_values["afrr_activated"] = self.add_indexes(market_border.afrr_activated, flow)
                case Product.FCRActivation:
                    updated_values["fcr_activated"] = self.add_indexes(market_border.fcr_activated, flow)

            # Update ReferenceFlow, otherwise the flow can be out of bounds for future markets
            updated_values["reference_flow"] = self.add_indexes_or_sum(market_border.reference_flow, flow)

            # Remark : Flow markets are not yet taken into account.
            # Update the Market Border
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
            updated_values: dict[str, Any] = {"name": critical_branch.name}
            flow = self.horizon_timeseries([0.0] * len(self.input_dataset.times))
            for market_area_ptdf in critical_branch.market_area_ptdf:
                da_ptdf = market_area_ptdf.da_ptdf.set_frequency(
                    self.input_dataset.parameters.temporal.timestep, False
                ).filter(self.input_dataset.times)  # type: ignore[arg-type]
                flow += da_ptdf

            match self.input_dataset.parameters.market:
                case Product.DayAhead:
                    updated_values["da_flow"] = self.add_indexes(critical_branch.da_flow, flow)
                case Product.Intraday:
                    updated_values["total_id_flow"] = self.add_indexes_or_sum(critical_branch.total_id_flow, flow)
                    updated_values["id_flow"] = self.add_timeseries_to_forecast(critical_branch.id_flow, flow)
                case _:
                    cfg.logger.info(
                        "ATLAS 1.3 does not support exports on critical branches for this market. "
                        "This should be corrected in future versions"
                    )
            change_sets.append(UpdateObject(updated_values, CriticalBranch))
        return change_sets

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

    def add_indexes(self, ts_obj: AbstractTimeseries | None, other: AbstractTimeseries) -> AbstractTimeseries:
        if ts_obj is None:
            return other
        if isinstance(ts_obj, LazyTimeseries):
            ts_obj = ts_obj.collect()
        if ts_obj.shape[0] < 2:
            return other
        if ts_obj.timestep > other.timestep:
            ts_obj.upsample(other.timestep)
        elif other.timestep > ts_obj.timestep:
            other.upsample(ts_obj.timestep)
        return ts_obj.add_indexes(other, inplace=False)

    def add_indexes_or_sum(self, ts_obj: AbstractTimeseries | None, other: Timeseries) -> AbstractTimeseries:
        if ts_obj is None:
            return other
        if isinstance(ts_obj, LazyTimeseries):
            ts_obj = ts_obj.collect()
        if ts_obj.timeseries.shape[0] < 2:
            return other
        if ts_obj.timestep > other.timestep:
            ts_obj.upsample(other.timestep)
        elif other.timestep > ts_obj.timestep:
            other.upsample(ts_obj.timestep)
        if other.index[0] not in ts_obj:
            return self.add_indexes(ts_obj, self.horizon_timeseries([0.0] * len(self.input_dataset.times)))
        else:
            ts_obj += other
            return ts_obj

    def add_timeseries_to_forecast(
        self, forecast_obj: ForecastingMatrix | LazyForecastingMatrix | None, other: Timeseries
    ) -> ForecastingMatrix | LazyForecastingMatrix:
        if forecast_obj is None:
            new_forecast_obj = ForecastingMatrix()
            new_forecast_obj.add(other, self.input_dataset.parameters.temporal.execution_date)
            return new_forecast_obj
        else:
            if isinstance(forecast_obj, LazyForecastingMatrix):
                forecast_obj = forecast_obj.collect()
            forecast_obj.add(other, self.input_dataset.parameters.temporal.execution_date)
            return forecast_obj
