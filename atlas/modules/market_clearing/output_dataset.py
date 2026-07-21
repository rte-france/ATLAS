"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.abstract_class.dataset import AbstractModuleOutput
from atlas.enums import Product
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.data_classes import ClearingOutputs
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.parameters import ExchangeConstraintsType, MarketClearingParameters
from atlas.objects.market.critical_branch import CriticalBranch
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market.market_border import MarketBorder
from atlas.objects.market.order import Order
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.orchestrator.change_set import UpdateObject
from atlas.timing import generate_datetimes


class MarketClearingOutputDataset(AbstractModuleOutput[MarketClearingParameters]):
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
        market_prices: dict[tuple[str, int], float],
    ):
        self.input_dataset = input_dataset
        self.accepted_powers = clearing_outputs.accepted_powers
        self.local_balances = clearing_outputs.local_balances
        self.border_exchanges = clearing_outputs.border_exchanges
        self.market_prices = market_prices

    def build_change_sets(self) -> None:
        self.update_orders()
        self.update_market_area()
        self.update_market_border()
        if self.input_dataset.parameters.exchange_constraints_type == ExchangeConstraintsType.FB:
            self.update_critical_branches()

    def update_orders(self):
        # If accepted power is too small then change it to 0
        # Update individual spread price for order
        for order_name, order in self.input_dataset.orders.items():
            updated_values = {"name": order_name}
            accepted_power = self.accepted_powers[order.market_area.name, order_name]
            # At this point, unaccepted orders can be skipped:
            if abs(accepted_power) <= self.input_dataset.parameters.allowed_round_off_error:
                continue
            updated_values["accepted_power"] = accepted_power
            time_index = order.time_index
            if time_index is None:
                continue
            # The surplus of an order is the gain made by its emitter computed from the present spot price:
            spot_price = self.market_prices[order.market_area.name, time_index]
            if order.is_sale:
                updated_values["individual_spread"] = spot_price - order.price
            else:
                updated_values["individual_spread"] = order.price - spot_price

            # Update the Order
            self.change_sets.append(UpdateObject(updated_values, Order))

        # Create accepted power TS for equipment and portfolio
        equipments_ts, portfolios_ts = {}, {}
        equipments_mapping, portfolios_mapping = {}, {}
        for order_name, order in self.input_dataset.orders.items():
            accepted_power = self.accepted_powers[order.market_area.name, order_name]
            # At this point, unaccepted orders can be skipped:
            if abs(accepted_power) <= self.input_dataset.parameters.allowed_round_off_error:
                continue
            if not order.is_agent_tso and order.equipment is not None:
                equipment = order.equipment
                if equipment is None:
                    continue
                portfolio = equipment.portfolio
                if portfolio is None:
                    continue
                if equipment.name not in equipments_ts:
                    equipments_ts[equipment.name] = Timeseries.from_index(
                        self.input_dataset.times[0],
                        self.input_dataset.parameters.temporal.timestep,
                        self.input_dataset.times[-1],
                        0.0,
                    )
                    equipments_mapping[equipment.name] = equipment
                if portfolio.name not in portfolios_ts:
                    portfolios_ts[portfolio.name] = Timeseries.from_index(
                        self.input_dataset.times[0],
                        self.input_dataset.parameters.temporal.timestep,
                        self.input_dataset.times[-1],
                        0.0,
                    )
                    portfolios_mapping[portfolio.name] = portfolio

                indexes = generate_datetimes(
                    order.start_date,
                    order.end_date_processed - self.input_dataset.parameters.temporal.timestep,
                    self.input_dataset.parameters.temporal.timestep,
                )
                values_sold = [accepted_power * order.production_sign for _ in range(len(indexes))]

                if len(values_sold) == 1:
                    equipments_ts[equipment.name].sum_value_at(order.start_date, values_sold[0])
                    portfolios_ts[portfolio.name].sum_value_at(order.start_date, values_sold[0])
                else:
                    value_sold_ts = Timeseries.from_values(
                        order.start_date, self.input_dataset.parameters.temporal.timestep, values_sold
                    )
                    equipments_ts[equipment.name] += value_sold_ts
                    portfolios_ts[portfolio.name] += value_sold_ts

        for equipment_name, equipment_ts in equipments_ts.items():
            equipment = equipments_mapping[equipment_name]
            updated_values = {"name": equipment_name}
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
            self.change_sets.append(UpdateObject(updated_values, type(equipment)))

        for portfolio_name, portfolio_ts in portfolios_ts.items():
            portfolio = portfolios_mapping[portfolio_name]
            updated_values = {"name": portfolio_name}
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
            self.change_sets.append(UpdateObject(updated_values, Portfolio))

    def update_market_area(self):
        for market_area_name, market_area in self.input_dataset.market_areas.items():
            updated_values = {"name": market_area_name}
            balance_values = [
                self.local_balances[market_area_name, time_index]
                for time_index, _ in enumerate(self.input_dataset.times)
            ]
            price_values = [
                self.market_prices[market_area_name, time_index]
                for time_index, _ in enumerate(self.input_dataset.times)
            ]

            values_bal = Timeseries.from_values(
                self.input_dataset.parameters.temporal.start_date,
                self.input_dataset.parameters.temporal.timestep,
                balance_values,
            )
            values_price = Timeseries.from_values(
                self.input_dataset.parameters.temporal.start_date,
                self.input_dataset.parameters.temporal.timestep,
                price_values,
            )

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
            self.change_sets.append(UpdateObject(updated_values, MarketArea))

    def update_market_border(self):
        for market_border_name, market_border in self.input_dataset.market_borders.items():
            updated_values = {"name": market_border_name}
            flow_values = [
                self.border_exchanges[market_border_name, time_index]
                for time_index, _ in enumerate(self.input_dataset.times)
            ]
            shadow_price_values = [
                self.market_prices[market_border.uphill_market_area.name, time_index]
                - self.market_prices[market_border.downhill_market_area.name, time_index]
                for time_index, _ in enumerate(self.input_dataset.times)
            ]

            flow = Timeseries.from_values(
                self.input_dataset.parameters.temporal.start_date,
                self.input_dataset.parameters.temporal.timestep,
                flow_values,
            )
            shadow_price = Timeseries.from_values(
                self.input_dataset.parameters.temporal.start_date,
                self.input_dataset.parameters.temporal.timestep,
                shadow_price_values,
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
            self.change_sets.append(UpdateObject(updated_values, MarketBorder))

    def update_critical_branches(self):
        relative_balances = {}
        for market_area_name, market_area in self.input_dataset.market_areas.items():
            for time_index, time in enumerate(self.input_dataset.times):
                relative_balances[market_area_name, time_index] = self.local_balances[
                    market_area_name, time_index
                ] - market_area.ref_balance.get_value(time)

        for critical_branch in self.input_dataset.critical_branches.values():
            updated_values = {"name": critical_branch.name}
            flow = Timeseries.from_index(
                self.input_dataset.times[0],
                self.input_dataset.parameters.temporal.timestep,
                self.input_dataset.times[-1],
                0.0,
            )
            for market_area_ptdf in critical_branch.market_area_ptdf:
                if market_area_ptdf.da_ptdf is None:
                    continue
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
            # Update the Critical branch
            self.change_sets.append(UpdateObject(updated_values, CriticalBranch))

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
            null_ts = Timeseries.from_index(
                self.input_dataset.times[0],
                self.input_dataset.parameters.temporal.timestep,
                self.input_dataset.times[-1],
                0.0,
            )
            return self.add_indexes(ts_obj, null_ts)
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
