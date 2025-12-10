"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
import atlas.config as cfg
from atlas import Timeseries, generate_datetimes
from atlas.enum import Product

from atlas.models.market.market_area import MarketArea
from atlas.models.market.market_border import MarketBorder
from atlas.models.market.critical_branch import CriticalBranch
from atlas.models.market.order import Order
from atlas.models.equipment.equipment import Equipment
from atlas.models.portfolio import Portfolio

from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.models.business_model import BusinessModel
from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters, ExchangeConstraintsType


class MarketClearingOutputDataset(AbstractDataset[MarketClearingParameters]):
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

    def __init__(self, input_dataset: MarketClearingInputDataset):
        self.input_dataset = input_dataset
        self.raw_data: dict[str, list[type[BusinessModel]]] = {}

    def run(
            self,
            accepted_powers: dict[tuple[str, str], float],
            local_balances: dict[tuple[str, int], float],
            border_exchanges: dict[tuple[str, int], float],
            market_prices: dict[tuple[str, int], float]
    ):
        self.update_raw_data_with_not_modified_business_model_object()
        self.update_business_model_object(accepted_powers, local_balances, border_exchanges,
                                                                    market_prices)
        self.update_raw_data_with_modified_business_model_object()

    def update_raw_data_with_not_modified_business_model_object(self):
        """ Update raw_data with business model object that have not changed"""
        for business_model_name in self.input_dataset.raw_data:
            if (cfg.MODEL_MAPPING_NAME[business_model_name] not in
                    MarketClearingOutputDataset.get_custom_business_model_object_modified()):
                self.raw_data[business_model_name] = self.input_dataset.raw_data[business_model_name]

        # Create not modified MarketArea
        market_area_business_object_str = cfg.INVERSE_MODEL_MAPPING_NAME[MarketArea]
        self.raw_data[market_area_business_object_str] = []
        for market_area in self.input_dataset.raw_data[market_area_business_object_str]:
            if market_area.name not in self.input_dataset.mc_market_areas:
                self.raw_data[market_area_business_object_str].append(market_area)
        # Create not modified MarketBorder
        market_border_business_object_str = cfg.INVERSE_MODEL_MAPPING_NAME[MarketBorder]
        self.raw_data[market_border_business_object_str] = []
        for market_border in self.input_dataset.raw_data[market_border_business_object_str]:
            if market_border.name not in self.input_dataset.mc_market_borders:
                self.raw_data[market_border_business_object_str].append(market_border)
        # Create not modified CriticalBranch
        critical_branch_business_object_str = cfg.INVERSE_MODEL_MAPPING_NAME[CriticalBranch]
        # If there is no critical branch (we may be in ATC
        if critical_branch_business_object_str in self.input_dataset.raw_data:
            self.raw_data[critical_branch_business_object_str] = []
            for critical_branch in self.input_dataset.raw_data[critical_branch_business_object_str]:
                if critical_branch.name not in self.input_dataset.mc_critical_branches:
                    self.raw_data[critical_branch_business_object_str].append(critical_branch)
        # Create not modified Order
        order_business_object_str = cfg.INVERSE_MODEL_MAPPING_NAME[Order]
        self.raw_data[order_business_object_str] = []
        for order in self.input_dataset.raw_data[order_business_object_str]:
            if order.name not in self.input_dataset.mc_orders:
                self.raw_data[order_business_object_str].append(order)

    def update_raw_data_with_modified_business_model_object(self):
        """ Update raw_data with business model object that have changed
        [MarketArea, MarketBorder, CriticalBranch, Order, Equipment, Portfolio]"""
        # Create modified MarketArea
        for mc_market_area in self.input_dataset.mc_market_areas.values():
            mc_market_area_dump = MarketClearingInputDataset.shallow_dump(mc_market_area)
            market_area = MarketArea.model_validate(mc_market_area_dump)
            self.raw_data[cfg.INVERSE_MODEL_MAPPING_NAME[MarketArea]].append(market_area)
        # Create modified MarketBorder
        for mc_market_border in self.input_dataset.mc_market_borders.values():
            mc_market_border_dump = MarketClearingInputDataset.shallow_dump(mc_market_border)
            market_border = MarketBorder.model_validate(mc_market_border_dump)
            self.raw_data[cfg.INVERSE_MODEL_MAPPING_NAME[MarketBorder]].append(market_border)
        # Create modified CriticalBranch
        for mc_critical_branch in self.input_dataset.mc_critical_branches.values():
            mc_critical_branch_dump = MarketClearingInputDataset.shallow_dump(mc_critical_branch)
            critical_branch = CriticalBranch.model_validate(mc_critical_branch_dump)
            self.raw_data[cfg.INVERSE_MODEL_MAPPING_NAME[CriticalBranch]].append(critical_branch)
        # Create modified Order
        for mc_order in self.input_dataset.mc_orders.values():
            mc_order_dump = MarketClearingInputDataset.shallow_dump(mc_order)
            order = Order.model_validate(mc_order_dump)
            self.raw_data[cfg.INVERSE_MODEL_MAPPING_NAME[Order]].append(order)


    def update_business_model_object(
            self,
            accepted_powers: dict[tuple[str, str], float],
            local_balances: dict[tuple[str, int], float],
            border_exchanges: dict[tuple[str, int], float],
            market_prices: dict[tuple[str, int], float]
    ):
        self.update_orders(accepted_powers, market_prices)
        self.update_market_area(local_balances, market_prices)
        self.update_market_border(border_exchanges, market_prices)
        if self.input_dataset.parameters.exchange_constraints_type == ExchangeConstraintsType.FB:
            self.update_critical_branches(local_balances)

    def update_orders(self, accepted_powers: dict[tuple[str, str], float], market_prices: dict[tuple[str, int], float]):
        # If accepted power is too small then change it to 0
        # Update individual spread price for order
        for order_name, mc_order in self.input_dataset.mc_orders.items():
            accepted_power = accepted_powers[mc_order.market_area.name, order_name]
            # At this point, unaccepted orders can be skipped:
            if abs(accepted_power) <= self.input_dataset.parameters.allowed_round_off_error:
                mc_order.accepted_power = 0
                continue
            mc_order.accepted_power = accepted_power
            # The surplus of an order is the gain made by its emitter computed from the present spot price:
            spot_price = market_prices[mc_order.market_area.name, mc_order.time_index]
            if mc_order.is_sale:
                mc_order.individual_spread = spot_price - mc_order.price
            else:
                mc_order.individual_spread = mc_order.price - spot_price

        # Create accepted power TS for equipment and portfolio
        equipments_ts, portfolios_ts = {}, {}
        equipments_mapping, portfolios_mapping = {}, {}
        for order_name, mc_order in self.input_dataset.mc_orders.items():
            accepted_power = accepted_powers[mc_order.market_area.name, order_name]
            # At this point, unaccepted orders can be skipped:
            if abs(accepted_power) <= self.input_dataset.parameters.allowed_round_off_error:
                continue
            if not mc_order.is_agent_tso and mc_order.equipment is not None:
                equipment = mc_order.equipment
                portfolio = equipment.portfolio
                if equipment.name not in equipments_ts:
                    equipments_ts[equipment.name] = Timeseries.from_index(
                        self.input_dataset.times[0],
                        self.input_dataset.parameters.time_step,
                        self.input_dataset.times[-1],
                        0.0
                    )
                    equipments_mapping[equipment.name] = equipment
                if portfolio.name not in portfolios_ts:
                    portfolios_ts[portfolio.name] = Timeseries.from_index(
                        self.input_dataset.times[0],
                        self.input_dataset.parameters.time_step,
                        self.input_dataset.times[-1],
                        0.0
                    )
                    portfolios_mapping[portfolio.name] = portfolio

                indexes = generate_datetimes(
                    mc_order.start_date,
                    mc_order.end_datetime - self.input_dataset.parameters.time_step,
                    self.input_dataset.parameters.time_step
                )
                values_sold = [mc_order.accepted_power * mc_order.production_sign for _ in range(len(indexes))]
                if len(values_sold) == 1:

                    equipments_ts[equipment.name].add_value_at(mc_order.start_date, values_sold[0])
                    portfolios_ts[portfolio.name].add_value_at(mc_order.start_date, values_sold[0])
                else:
                    value_sold_ts= Timeseries.from_values(mc_order.start_date,
                                                               self.input_dataset.parameters.time_step, values_sold)
                    equipments_ts[equipment.name] += value_sold_ts
                    portfolios_ts[portfolio.name] += value_sold_ts

        for equipment_name, equipment_ts in equipments_ts.items():
            equipment = equipments_mapping[equipment_name]
            match self.input_dataset.parameters.market:
                case Product.DayAhead:
                    equipment.da_cleared_quantity = equipment_ts
                case Product.AFRRUpProcurement:
                    equipment.afrr_up_procured = equipment_ts
                case Product.AFRRDownProcurement:
                    equipment.afrr_down_procured = equipment_ts
                case Product.MFRRUpProcurement:
                    equipment.mfrr_up_procured = equipment_ts
                case Product.MFRRDownProcurement:
                    equipment.mfrr_down_procured = equipment_ts
                case Product.RRUpProcurement:
                    equipment.rr_up_procured = equipment_ts
                case Product.RRDownProcurement:
                    equipment.rr_down_procured = equipment_ts
                case Product.AFRRActivation:
                    equipment.afrr_activated = equipment_ts
                case Product.MFRRActivation:
                    equipment.mfrr_activated = equipment_ts
                case Product.RRActivation:
                    equipment.rr_activated = equipment_ts
                case Product.FCRActivation:
                    equipment.fcr_activated = equipment_ts
                case Product.Intraday:
                    equipment.total_id_cleared_quantity = equipment_ts
                    equipment.id_cleared_quantity.replace(self.input_dataset.parameters.execution_date,
                                                          equipment_ts)

        for portfolio_name, portfolio_ts in portfolios_ts.items():
            portfolio = portfolios_mapping[portfolio_name]
            match self.input_dataset.parameters.market:
                case Product.DayAhead:
                    portfolio.da_cleared_quantity = portfolio_ts
                case Product.AFRRUpProcurement:
                    portfolio.afrr_up_procured = portfolio_ts
                case Product.AFRRDownProcurement:
                    portfolio.afrr_down_procured = portfolio_ts
                case Product.MFRRUpProcurement:
                    portfolio.mfrr_up_procured = portfolio_ts
                case Product.MFRRDownProcurement:
                    portfolio.mfrr_down_procured = portfolio_ts
                case Product.RRUpProcurement:
                    portfolio.rr_up_procured = portfolio_ts
                case Product.RRDownProcurement:
                    portfolio.rr_down_procured = portfolio_ts
                case Product.AFRRActivation:
                    portfolio.afrr_activated = portfolio_ts
                case Product.MFRRActivation:
                    portfolio.mfrr_activated = portfolio_ts
                case Product.RRActivation:
                    portfolio.rr_activated = portfolio_ts
                case Product.FCRActivation:
                    portfolio.fcr_activated = portfolio_ts
                case Product.Intraday:
                    portfolio.total_id_cleared_quantity = portfolio_ts
                    portfolio.id_cleared_quantity.replace(self.input_dataset.parameters.execution_date,
                                                          portfolio_ts)

    def update_market_area(self, local_balances: dict[tuple[str, int], float],
                           market_prices: dict[tuple[str, int], float]):
        for market_area_name, mc_market_area in self.input_dataset.mc_market_areas.items():
            balance_values = [local_balances[market_area_name, time_index] for time_index, _ in enumerate(self.input_dataset.times)]
            price_values = [market_prices[market_area_name, time_index] for time_index, _ in enumerate(self.input_dataset.times)]

            values_bal = Timeseries.from_values(
                self.input_dataset.parameters.start_date,
                self.input_dataset.parameters.time_step,
                balance_values
            )
            values_price = Timeseries.from_values(
                self.input_dataset.parameters.start_date,
                self.input_dataset.parameters.time_step,
                price_values
            )

            match self.input_dataset.parameters.market:
                case Product.DayAhead:
                    mc_market_area.da_balance = self.update_timeseries(mc_market_area.da_balance, values_bal)
                    mc_market_area.da_price = self.update_timeseries(mc_market_area.da_price, values_bal)
                case Product.Intraday:
                    mc_market_area.total_id_balance = self.add_timeseries(mc_market_area.total_id_balance, values_bal)
                    mc_market_area.id_balance = self.update_forecast_timeseries(
                        mc_market_area.id_balance, values_bal)
                    mc_market_area.id_price = self.update_forecast_timeseries(
                        mc_market_area.id_price, values_price)
                case Product.RRActivation:
                    mc_market_area.rr_activation_price = self.update_timeseries(mc_market_area.rr_activation_price, values_price)
                    mc_market_area.rr_activation_balance = self.update_timeseries(mc_market_area.rr_activation_balance, values_bal)
                case Product.MFRRActivation:
                    mc_market_area.mfrr_activation_price = self.update_timeseries(mc_market_area.mfrr_activation_price, values_price)
                    mc_market_area.mfrr_activation_balance = self.update_timeseries(mc_market_area.mfrr_activation_balance, values_bal)
                case Product.AFRRActivation:
                    mc_market_area.afrr_activation_price = self.update_timeseries(mc_market_area.afrr_activation_price, values_price)
                case Product.FCRActivation:
                    mc_market_area.fcr_activation_price = self.update_timeseries(mc_market_area.fcr_activation_price, values_price)

    def update_market_border(self, border_exchanges: dict[tuple[str, int], float],
                             market_prices: dict[tuple[str, int], float]):
        for market_border_name, mc_market_border in self.input_dataset.mc_market_borders.items():

            flow_values = [border_exchanges[market_border_name, time_index]
                           for time_index, _ in enumerate(self.input_dataset.times)]
            shadow_price_values = [
                market_prices[mc_market_border.uphill_market_area.name, time_index] -
                market_prices[mc_market_border.downhill_market_area.name, time_index]
                for time_index, _ in enumerate(self.input_dataset.times)]

            flow = Timeseries.from_values(
                self.input_dataset.parameters.start_date,
                self.input_dataset.parameters.time_step,
                flow_values
            )
            shadow_price = Timeseries.from_values(
                self.input_dataset.parameters.start_date,
                self.input_dataset.parameters.time_step,
                shadow_price_values
            )
            match self.input_dataset.parameters.market:
                case Product.DayAhead:
                    mc_market_border.da_flow = self.update_timeseries(
                        mc_market_border.da_flow, flow)
                    mc_market_border.da_shadow_price = self.update_timeseries(
                                mc_market_border.da_shadow_price, shadow_price)
                case Product.Intraday:
                    mc_market_border.total_id_flow = self.add_timeseries(
                        mc_market_border.total_id_flow, flow)
                    mc_market_border.id_flow = self.update_forecast_timeseries(
                        mc_market_border.id_flow, flow)
                    mc_market_border.id_shadow_price = self.update_forecast_timeseries(
                        mc_market_border.id_shadow_price, shadow_price)
                case Product.MFRRUpProcurement:
                    mc_market_border.mfrr_up_procured = self.update_timeseries(
                        mc_market_border.mfrr_up_procured, flow)
                case Product.MFRRDownProcurement:
                    mc_market_border.mfrr_down_procured = self.update_timeseries(
                        mc_market_border.mfrr_down_procured, flow)
                case Product.AFRRUpProcurement:
                    mc_market_border.afrr_up_procured = self.update_timeseries(
                        mc_market_border.afrr_up_procured, flow)
                case Product.AFRRDownProcurement:
                    mc_market_border.afrr_down_procured = self.update_timeseries(
                        mc_market_border.afrr_down_procured, flow)
                case Product.RRUpProcurement:
                    mc_market_border.rr_up_procured = self.update_timeseries(
                        mc_market_border.rr_up_procured, flow)
                case Product.RRDownProcurement:
                    mc_market_border.rr_down_procured = self.update_timeseries(
                        mc_market_border.rr_down_procured, flow)
                case Product.RRActivation:
                    mc_market_border.rr_activated = self.update_timeseries(
                        mc_market_border.rr_activated, flow)
                case Product.MFRRActivation:
                    mc_market_border.mfrr_activated = self.update_timeseries(
                        mc_market_border.mfrr_activated, flow)
                case Product.AFRRActivation:
                    mc_market_border.afrr_activated = self.update_timeseries(
                        mc_market_border.afrr_activated, flow)
                case Product.FCRActivation:
                    mc_market_border.fcr_activated = self.update_timeseries(
                        mc_market_border.fcr_activated, flow)

            # FC: Update ReferenceFlow, otherwise the flow can be out of bounds for future markets
            mc_market_border.reference_flow = self.update_timeseries(
                mc_market_border.reference_flow, flow)

            # Remark : Flow markets are not yet taken into account.

    def update_critical_branches(self, local_balance: dict[tuple[str, int], float]):
        relative_balances = {}
        for market_area_name, mc_market_area in self.input_dataset.mc_market_areas.items():
            for time_index, time in enumerate(self.input_dataset.times):
                relative_balances[market_area_name, time_index] = (local_balance[market_area_name, time_index] -
                                                                   mc_market_area.ref_balance.get_value(time))

        for critical_branch_name, mc_critical_branch in self.input_dataset.mc_critical_branches.items():
            flow_values = [
                sum([mc_market_area_ptdf.da_ptdf.get_value(time)
                     for mc_market_area_ptdf in mc_critical_branch.market_area_ptdf])
                for time_index, time in enumerate(self.input_dataset.times)]

            flow = Timeseries.from_values(
                self.input_dataset.parameters.start_date,
                self.input_dataset.parameters.time_step,
                flow_values
            )
            match self.input_dataset.parameters.market:
                case Product.DayAhead:
                    mc_critical_branch.da_flow = self.update_timeseries(
                        mc_critical_branch.da_flow, flow)
                case Product.Intraday:
                    mc_critical_branch.total_id_flow = self.add_timeseries(
                        mc_critical_branch.total_id_flow, flow)
                    mc_critical_branch.id_flow = self.update_forecast_timeseries(
                        mc_critical_branch.id_flow, flow)
                case _:
                    cfg.logger.info("ATLAS 1.3 does not support exports on critical branches for this market. "
                                "This should be corrected in future versions")

    def add_timeseries(self, ts_obj, ts_to_add):
        """
        Updates a timeseries:
        - if None → assign new_ts
        - else → align timestep and add new values
        """
        if ts_obj is None or len(ts_obj) < 2:
            return ts_to_add

        if ts_obj.timestep != self.input_dataset.parameters.time_step:
            ts_obj.set_frequency(self.input_dataset.parameters.time_step)

        ts_obj += ts_to_add
        return ts_obj

    def update_timeseries(self, ts_obj, new_ts):
        """
        Updates a timeseries:
        - if None → assign new_ts
        - else → align timestep and add new values
        """
        if ts_obj is None or len(ts_obj) < 2:
            return new_ts

        if ts_obj.timestep != self.input_dataset.parameters.time_step:
            ts_obj.set_frequency(self.input_dataset.parameters.time_step)

        ts_obj.set_values(new_ts, inplace=False)
        return ts_obj

    def update_forecast_timeseries(self, forecast_obj, ts_to_add):
        if self.input_dataset.parameters.execution_date not in forecast_obj.indexes:
            forecast_obj.add(ts_to_add, self.input_dataset.parameters.execution_date)
        else:
            old_ts = forecast_obj.get(self.input_dataset.parameters.execution_date)
            old_ts.set_frequency(self.input_dataset.parameters.time_step)
            forecast_obj.replace(self.input_dataset.parameters.execution_date,
                                                  old_ts + ts_to_add)
        return forecast_obj

    @staticmethod
    def get_custom_business_model_object_modified() -> list[type[BusinessModel]]:
        return [MarketArea, MarketBorder, CriticalBranch, Order]

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return [MarketArea, MarketBorder, CriticalBranch, Order, Equipment, Portfolio]
