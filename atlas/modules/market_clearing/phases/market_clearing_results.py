"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import polars as pl

from atlas import LazyForecastingMatrix
from atlas.enum import OrderType, Product
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.parameters import MarketClearingParameters


class MarketClearingResults:
    """
    Module storing the fourth and last step of the Market Clearing process: maximizing the accepted volumes of marginal
    orders.

    The previous steps have determined which orders could be associated with each others in order to maximize the
    social welfare, which exchanges it induced at borders and what were the resulting market prices. However, some
    orders which price is equal to the market price might remain unaccepted, whereas their price is equal to the market
    price. Indeed, their acceptance would not modify the overall social welfare. The present step is dedicated to
    finding such orders, called "marginal", and maximizing the volumes they can trade.
    """

    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        self.input_dataset = input_dataset
        self.parameters = parameters

    def run(self) -> None:
        if self.parameters.export_csv:
            if not self.parameters.output_path.exists():
                self.parameters.output_path.mkdir(parents=True, exist_ok=True)
            self.export_offers()
            self.export_market_areas_data()
            self.export_couplings_data()
            self.export_borders_data()

    def export_offers(self):
        offers = pl.DataFrame(
            schema={
                "Name": pl.Utf8,
                "IsAgentTSO": pl.Boolean,
                "Equipment": pl.Utf8,
                "MarketArea": pl.Utf8,
                "StartDate": pl.Datetime(time_zone="UTC"),
                "EndDate": pl.Datetime(time_zone="UTC"),
                "ExecutionDate": pl.Datetime(time_zone="UTC"),
                "OrderType": pl.Utf8,
                "isSell": pl.Boolean,
                "Product": pl.Utf8,
                "Qmin": pl.Float64,
                "Qmax": pl.Float64,
                "Price": pl.Float64,
                "AcceptedPower": pl.Float64,
            }
        )
        for order_name, mc_order in self.input_dataset.mc_orders.items():
            order_dict = {
                "Name": order_name,
                "IsAgentTSO": mc_order.is_agent_tso,
                "Equipment": mc_order.equipment.name if not mc_order.is_agent_tso else "NA",
                "MarketArea": mc_order.market_area.name,
                "StartDate": mc_order.start_date,
                "EndDate": mc_order.end_date,
                "ExecutionDate": mc_order.execution_date,
                "OrderType": mc_order.order_type.value,
                "isSell": True if mc_order.order_type == OrderType.Sell else False,
                "Product": mc_order.product.value,
                "Qmin": mc_order.qmin,
                "Qmax": mc_order.qmax,
                "Price": mc_order.price,
                "AcceptedPower": mc_order.accepted_power,
            }
            offer = pl.DataFrame({k: [v] for k, v in order_dict.items()})
            if offers is None:
                offers = offer
            else:
                offers.extend(offer.cast(offers.schema))
        offers.write_csv(self.parameters.output_path / "offers.csv")

    def export_market_areas_data(self):
        if self.parameters.market == Product.DayAhead:
            market_area_data = self.create_day_ahead_market_areas_data()
        elif self.parameters.market == Product.Intraday:
            market_area_data = self.create_intraday_market_areas_data()
        elif self.parameters.market == Product.RRActivation:
            market_area_data = self.create_rr_market_areas_data()
        else:
            # Consider only MFRRActivation
            market_area_data = self.create_mfrr_market_areas_data()
        market_area_data.write_csv(self.parameters.output_path / "market_area_data.csv")

    def create_day_ahead_market_areas_data(self) -> pl.DataFrame:
        market_areas_data = pl.DataFrame(
            schema={
                "Name": pl.Utf8,
                "TimeStep": pl.Datetime(time_zone="UTC"),
                "DAPrice": pl.Float64,
                "DABalance": pl.Float64,
            }
        )
        for market_area_name, mc_market_area in self.input_dataset.mc_market_areas.items():
            for time in self.input_dataset.times:
                market_area_dict = {
                    "Name": market_area_name,
                    "TimeStep": time,
                    "DAPrice": mc_market_area.da_price.get_value(time) if mc_market_area.da_price is not None else 0,
                    "DABalance": mc_market_area.da_balance.get_value(time)
                    if mc_market_area.da_balance is not None
                    else 0,
                }
                market_area_data = pl.DataFrame({k: [v] for k, v in market_area_dict.items()})
                market_areas_data.extend(market_area_data.cast(market_areas_data.schema))

        return market_areas_data

    def create_intraday_market_areas_data(self) -> pl.DataFrame:
        market_areas_data = pl.DataFrame(
            schema={
                "Name": pl.Utf8,
                "TimeStep": pl.Datetime(time_zone="UTC"),
                "IDPrice": pl.Float64,
                "TotalIDBalance": pl.Float64,
            }
        )
        for market_area_name, mc_market_area in self.input_dataset.mc_market_areas.items():
            id_price_forecast = mc_market_area.id_price
            id_balance_forecast = mc_market_area.id_balance
            if id_price_forecast is None or id_balance_forecast is None:
                continue

            if isinstance(id_price_forecast, LazyForecastingMatrix):
                id_price_forecast = id_price_forecast.collect()
            if isinstance(id_balance_forecast, LazyForecastingMatrix):
                id_balance_forecast = id_balance_forecast.collect()

            id_price_ts = id_price_forecast.select(self.parameters.execution_date)
            id_balance_ts = id_balance_forecast.select(self.parameters.execution_date)

            if id_price_ts is not None:
                id_price_ts = id_price_ts.set_frequency(self.input_dataset.parameters.timestep, False).filter(
                    self.input_dataset.times  # type: ignore[arg-type]
                )
            if id_balance_ts is not None:
                id_balance_ts = id_balance_ts.set_frequency(self.input_dataset.parameters.timestep, False).filter(
                    self.input_dataset.times  # type: ignore[arg-type]
                )

            for time in self.input_dataset.times:
                id_price: float = id_price_ts.get_value(time) if id_price_ts is not None else 0
                id_balance = id_balance_ts.get_value(time) if id_balance_ts is not None else 0
                market_area_dict = {
                    "Name": market_area_name,
                    "TimeStep": time,
                    "IDPrice": id_price,
                    "TotalIDBalance": id_balance,
                }
                market_area_data = pl.DataFrame({k: [v] for k, v in market_area_dict.items()})
                market_areas_data.extend(market_area_data.cast(market_areas_data.schema))
        return market_areas_data

    def create_rr_market_areas_data(self) -> pl.DataFrame:
        market_areas_data = pl.DataFrame(
            schema={
                "Name": pl.Utf8,
                "TimeStep": pl.Datetime(time_zone="UTC"),
                "RRActivationPrice": pl.Float64,
                "RRActivationBalance": pl.Float64,
            }
        )
        for market_area_name, mc_market_area in self.input_dataset.mc_market_areas.items():
            for time in self.input_dataset.times:
                market_area_dict = {
                    "Name": market_area_name,
                    "TimeStep": time,
                    "RRActivationPrice": mc_market_area.rr_activation_price.get_value(time)
                    if mc_market_area.rr_activation_price is not None
                    else 0,
                    "RRActivationBalance": mc_market_area.rr_activation_balance.get_value(time)
                    if mc_market_area.rr_activation_balance is not None
                    else 0,
                }
                market_area_data = pl.DataFrame({k: [v] for k, v in market_area_dict.items()})
                market_areas_data.extend(market_area_data.cast(market_areas_data.schema))
        return market_areas_data

    def create_mfrr_market_areas_data(self) -> pl.DataFrame:
        market_areas_data = pl.DataFrame(
            schema={
                "Name": pl.Utf8,
                "TimeStep": pl.Datetime(time_zone="UTC"),
                "MFRRActivationPrice": pl.Float64,
                "MFRRActivationBalance": pl.Float64,
            }
        )
        for market_area_name, mc_market_area in self.input_dataset.mc_market_areas.items():
            for time in self.input_dataset.times:
                market_area_dict = {
                    "Name": market_area_name,
                    "TimeStep": time,
                    "MFRRActivationPrice": mc_market_area.mfrr_activation_price.get_value(time)
                    if mc_market_area.mfrr_activation_price is not None
                    else 0,
                    "MFRRActivationBalance": mc_market_area.mfrr_activation_balance.get_value(time)
                    if mc_market_area.mfrr_activation_balance is not None
                    else 0,
                }
                market_area_data = pl.DataFrame({k: [v] for k, v in market_area_dict.items()})
                market_areas_data.extend(market_area_data.cast(market_areas_data.schema))
        return market_areas_data

    def export_couplings_data(self):
        couplings_data = pl.DataFrame(
            schema={
                "Name": pl.Utf8,
                "Type": pl.Utf8,
                "OrderList": pl.Utf8,
            }
        )
        for order_coupling_name, mc_order_coupling in self.input_dataset.mc_order_couplings.items():
            coupling_dict = {
                "Name": order_coupling_name,
                "Type": mc_order_coupling.coupling_type.value,
                "OrderList": ":".join([order.name for order in mc_order_coupling.orders]),
            }
            coupling_data = pl.DataFrame({k: [v] for k, v in coupling_dict.items()})
            couplings_data.extend(coupling_data.cast(couplings_data.schema))
        couplings_data.write_csv(self.parameters.output_path / "coupling_data.csv")

    def export_borders_data(self):
        if self.parameters.market == Product.DayAhead:
            borders_data = self.create_day_ahead_borders_data()
        elif self.parameters.market == Product.Intraday:
            borders_data = self.create_intraday_borders_data()
        elif self.parameters.market == Product.RRActivation:
            borders_data = self.create_rr_borders_data()
        else:
            # Consider only MFRRActivation
            borders_data = self.create_mfrr_borders_data()

        borders_data.write_csv(self.parameters.output_path / "border.csv")

    def create_day_ahead_borders_data(self) -> pl.DataFrame:
        market_borders_data = pl.DataFrame(
            schema={
                "Name": pl.Utf8,
                "TimeStep": pl.Datetime(time_zone="UTC"),
                "MaximumFlow": pl.Float64,
                "MinimumFlow": pl.Float64,
                "TotalFlow": pl.Float64,
                "DAFlow": pl.Float64,
            }
        )
        for market_border_name, mc_market_border in self.input_dataset.mc_market_borders.items():
            for time in self.input_dataset.times:
                market_border_dict = {
                    "Name": market_border_name,
                    "TimeStep": time,
                    "MaximumFlow": mc_market_border.maximum_flow.get_value(time)
                    if mc_market_border.maximum_flow is not None
                    else 0,
                    "MinimumFlow": mc_market_border.minimum_flow.get_value(time)
                    if mc_market_border.minimum_flow is not None
                    else 0,
                    "TotalFlow": mc_market_border.da_flow.get_value(time)
                    if mc_market_border.da_flow is not None
                    else 0,
                    "DAFlow": mc_market_border.da_flow.get_value(time) if mc_market_border.da_flow is not None else 0,
                }
                market_border_data = pl.DataFrame({k: [v] for k, v in market_border_dict.items()})
                market_borders_data.extend(market_border_data.cast(market_borders_data.schema))
        return market_borders_data

    def create_intraday_borders_data(self) -> pl.DataFrame:
        market_borders_data = pl.DataFrame(
            schema={
                "Name": pl.Utf8,
                "TimeStep": pl.Datetime(time_zone="UTC"),
                "MaximumFlow": pl.Float64,
                "MinimumFlow": pl.Float64,
                "TotalFlow": pl.Float64,
                "TotalIDFlow": pl.Float64,
            }
        )
        for market_border_name, mc_market_border in self.input_dataset.mc_market_borders.items():
            for time in self.input_dataset.times:
                total_flow = mc_market_border.da_flow.get_value(time) if mc_market_border.da_flow is not None else 0
                total_flow += (
                    mc_market_border.total_id_flow.get_value(time) if mc_market_border.total_id_flow is not None else 0
                )
                market_border_dict = {
                    "Name": market_border_name,
                    "TimeStep": time,
                    "MaximumFlow": mc_market_border.maximum_flow.get_value(time)
                    if mc_market_border.maximum_flow is not None
                    else 0,
                    "MinimumFlow": mc_market_border.minimum_flow.get_value(time)
                    if mc_market_border.minimum_flow is not None
                    else 0,
                    "TotalFlow": total_flow,
                    "TotalIDFlow": mc_market_border.total_id_flow.get_value(time)
                    if mc_market_border.total_id_flow is not None
                    else 0,
                }
                market_border_data = pl.DataFrame({k: [v] for k, v in market_border_dict.items()})
                market_borders_data.extend(market_border_data.cast(market_borders_data.schema))
        return market_borders_data

    def create_rr_borders_data(self) -> pl.DataFrame:
        market_borders_data = pl.DataFrame(
            schema={
                "Name": pl.Utf8,
                "TimeStep": pl.Datetime(time_zone="UTC"),
                "MaximumFlow": pl.Float64,
                "MinimumFlow": pl.Float64,
                "TotalFlow": pl.Float64,
                "RRActivated": pl.Float64,
            }
        )
        for market_border_name, mc_market_border in self.input_dataset.mc_market_borders.items():
            for time in self.input_dataset.times:
                total_flow = mc_market_border.da_flow.get_value(time) if mc_market_border.da_flow is not None else 0
                total_flow += (
                    mc_market_border.total_id_flow.get_value(time) if mc_market_border.total_id_flow is not None else 0
                )
                total_flow += (
                    mc_market_border.rr_activated.get_value(time) if mc_market_border.rr_activated is not None else 0
                )
                market_border_dict = {
                    "Name": market_border_name,
                    "TimeStep": time,
                    "MaximumFlow": mc_market_border.maximum_flow.get_value(time)
                    if mc_market_border.maximum_flow is not None
                    else 0,
                    "MinimumFlow": mc_market_border.minimum_flow.get_value(time)
                    if mc_market_border.minimum_flow is not None
                    else 0,
                    "TotalFlow": total_flow,
                    "RRActivated": mc_market_border.rr_activated.get_value(time)
                    if mc_market_border.rr_activated is not None
                    else 0,
                }
                market_border_data = pl.DataFrame({k: [v] for k, v in market_border_dict.items()})
                market_borders_data.extend(market_border_data.cast(market_borders_data.schema))
        return market_borders_data

    def create_mfrr_borders_data(self) -> pl.DataFrame:
        market_borders_data = pl.DataFrame(
            schema={
                "Name": pl.Utf8,
                "TimeStep": pl.Datetime(time_zone="UTC"),
                "MaximumFlow": pl.Float64,
                "MinimumFlow": pl.Float64,
                "TotalFlow": pl.Float64,
                "MFRRActivated": pl.Float64,
            }
        )
        for market_border_name, mc_market_border in self.input_dataset.mc_market_borders.items():
            for time in self.input_dataset.times:
                total_flow = mc_market_border.da_flow.get_value(time) if mc_market_border.da_flow is not None else 0
                total_flow += (
                    mc_market_border.total_id_flow.get_value(time) if mc_market_border.total_id_flow is not None else 0
                )
                total_flow += (
                    mc_market_border.rr_activated.get_value(time) if mc_market_border.rr_activated is not None else 0
                )
                total_flow += (
                    mc_market_border.mfrr_activated.get_value(time)
                    if mc_market_border.mfrr_activated is not None
                    else 0
                )
                market_border_dict = {
                    "Name": market_border_name,
                    "TimeStep": time,
                    "MaximumFlow": mc_market_border.maximum_flow.get_value(time)
                    if mc_market_border.maximum_flow is not None
                    else 0,
                    "MinimumFlow": mc_market_border.minimum_flow.get_value(time)
                    if mc_market_border.minimum_flow is not None
                    else 0,
                    "TotalFlow": total_flow,
                    "MFRRActivated": mc_market_border.mfrr_activated.get_value(time)
                    if mc_market_border.mfrr_activated is not None
                    else 0,
                }
                market_border_data = pl.DataFrame({k: [v] for k, v in market_border_dict.items()})
                market_borders_data.extend(market_border_data.cast(market_borders_data.schema))
        return market_borders_data
