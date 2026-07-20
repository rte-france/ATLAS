"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

import polars as pl

from atlas.enums import OrderType, Product
from atlas.math.forecasting_matrix import LazyForecastingMatrix
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.parameters import MarketClearingParameters


def value_or_zero(ts, time) -> float:
    return ts.get_value(time) if ts is not None else 0


def build_rows_dataframe(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(rows, schema=schema)


class MarketClearingResults:
    """
    Exports the results of the Market Clearing process to CSV: accepted offers, market area data, order
    couplings and border data. Only instantiated by the module when result export is requested.
    """

    def __init__(
        self,
        input_dataset: MarketClearingInputDataset,
        parameters: MarketClearingParameters,
        accepted_powers: dict[tuple[str, str], float],
    ):
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.accepted_powers = accepted_powers

    def compute(self) -> None:
        if not self.parameters.get_output_results_dir().exists():
            self.parameters.get_output_results_dir().mkdir(parents=True, exist_ok=True)
        self.export_offers()
        self.export_market_areas_data()
        self.export_couplings_data()
        self.export_borders_data()

    def export_offers(self):
        schema = {
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
        rows = []
        for order_name, mc_order in self.input_dataset.mc_orders.items():
            rows.append(
                {
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
                    "AcceptedPower": self.accepted_powers[mc_order.market_area.name, order_name],
                }
            )
        build_rows_dataframe(rows, schema).write_csv(self.parameters.get_output_results_dir() / "offers.csv")

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
        market_area_data.write_csv(self.parameters.get_output_results_dir() / "market_area_data.csv")

    def create_day_ahead_market_areas_data(self) -> pl.DataFrame:
        schema = {
            "Name": pl.Utf8,
            "TimeStep": pl.Datetime(time_zone="UTC"),
            "DAPrice": pl.Float64,
            "DABalance": pl.Float64,
        }
        rows = [
            {
                "Name": market_area_name,
                "TimeStep": time,
                "DAPrice": value_or_zero(mc_market_area.da_price, time),
                "DABalance": value_or_zero(mc_market_area.da_balance, time),
            }
            for market_area_name, mc_market_area in self.input_dataset.mc_market_areas.items()
            for time in self.input_dataset.times
        ]
        return build_rows_dataframe(rows, schema)

    def create_intraday_market_areas_data(self) -> pl.DataFrame:
        schema = {
            "Name": pl.Utf8,
            "TimeStep": pl.Datetime(time_zone="UTC"),
            "IDPrice": pl.Float64,
            "TotalIDBalance": pl.Float64,
        }
        rows = []
        for market_area_name, mc_market_area in self.input_dataset.mc_market_areas.items():
            id_price_forecast = mc_market_area.id_price
            id_balance_forecast = mc_market_area.id_balance
            if id_price_forecast is None or id_balance_forecast is None:
                continue

            if isinstance(id_price_forecast, LazyForecastingMatrix):
                id_price_forecast = id_price_forecast.collect()
            if isinstance(id_balance_forecast, LazyForecastingMatrix):
                id_balance_forecast = id_balance_forecast.collect()

            id_price_ts = id_price_forecast.select(self.parameters.temporal.execution_date)
            id_balance_ts = id_balance_forecast.select(self.parameters.temporal.execution_date)

            if id_price_ts is not None:
                id_price_ts = id_price_ts.set_frequency(self.input_dataset.parameters.temporal.timestep, False).filter(
                    self.input_dataset.times  # type: ignore[arg-type]
                )
            if id_balance_ts is not None:
                id_balance_ts = id_balance_ts.set_frequency(
                    self.input_dataset.parameters.temporal.timestep, False
                ).filter(
                    self.input_dataset.times  # type: ignore[arg-type]
                )

            for time in self.input_dataset.times:
                rows.append(
                    {
                        "Name": market_area_name,
                        "TimeStep": time,
                        "IDPrice": value_or_zero(id_price_ts, time),
                        "TotalIDBalance": value_or_zero(id_balance_ts, time),
                    }
                )
        return build_rows_dataframe(rows, schema)

    def create_rr_market_areas_data(self) -> pl.DataFrame:
        schema = {
            "Name": pl.Utf8,
            "TimeStep": pl.Datetime(time_zone="UTC"),
            "RRActivationPrice": pl.Float64,
            "RRActivationBalance": pl.Float64,
        }
        rows = [
            {
                "Name": market_area_name,
                "TimeStep": time,
                "RRActivationPrice": value_or_zero(mc_market_area.rr_activation_price, time),
                "RRActivationBalance": value_or_zero(mc_market_area.rr_activation_balance, time),
            }
            for market_area_name, mc_market_area in self.input_dataset.mc_market_areas.items()
            for time in self.input_dataset.times
        ]
        return build_rows_dataframe(rows, schema)

    def create_mfrr_market_areas_data(self) -> pl.DataFrame:
        schema = {
            "Name": pl.Utf8,
            "TimeStep": pl.Datetime(time_zone="UTC"),
            "MFRRActivationPrice": pl.Float64,
            "MFRRActivationBalance": pl.Float64,
        }
        rows = [
            {
                "Name": market_area_name,
                "TimeStep": time,
                "MFRRActivationPrice": value_or_zero(mc_market_area.mfrr_activation_price, time),
                "MFRRActivationBalance": value_or_zero(mc_market_area.mfrr_activation_balance, time),
            }
            for market_area_name, mc_market_area in self.input_dataset.mc_market_areas.items()
            for time in self.input_dataset.times
        ]
        return build_rows_dataframe(rows, schema)

    def export_couplings_data(self):
        schema = {
            "Name": pl.Utf8,
            "Type": pl.Utf8,
            "OrderList": pl.Utf8,
        }
        rows = [
            {
                "Name": order_coupling_name,
                "Type": mc_order_coupling.coupling_type.value,
                "OrderList": "|".join([order.name for order in mc_order_coupling.orders]),
            }
            for order_coupling_name, mc_order_coupling in self.input_dataset.mc_order_couplings.items()
        ]
        build_rows_dataframe(rows, schema).write_csv(self.parameters.get_output_results_dir() / "coupling_data.csv")

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

        borders_data.write_csv(self.parameters.get_output_results_dir() / "border.csv")

    def create_day_ahead_borders_data(self) -> pl.DataFrame:
        schema = {
            "Name": pl.Utf8,
            "TimeStep": pl.Datetime(time_zone="UTC"),
            "MaximumFlow": pl.Float64,
            "MinimumFlow": pl.Float64,
            "TotalFlow": pl.Float64,
            "DAFlow": pl.Float64,
        }
        rows = [
            {
                "Name": market_border_name,
                "TimeStep": time,
                "MaximumFlow": value_or_zero(mc_market_border.maximum_flow, time),
                "MinimumFlow": value_or_zero(mc_market_border.minimum_flow, time),
                "TotalFlow": value_or_zero(mc_market_border.da_flow, time),
                "DAFlow": value_or_zero(mc_market_border.da_flow, time),
            }
            for market_border_name, mc_market_border in self.input_dataset.mc_market_borders.items()
            for time in self.input_dataset.times
        ]
        return build_rows_dataframe(rows, schema)

    def create_intraday_borders_data(self) -> pl.DataFrame:
        schema = {
            "Name": pl.Utf8,
            "TimeStep": pl.Datetime(time_zone="UTC"),
            "MaximumFlow": pl.Float64,
            "MinimumFlow": pl.Float64,
            "TotalFlow": pl.Float64,
            "TotalIDFlow": pl.Float64,
        }
        rows = []
        for market_border_name, mc_market_border in self.input_dataset.mc_market_borders.items():
            for time in self.input_dataset.times:
                total_flow = value_or_zero(mc_market_border.da_flow, time)
                total_flow += value_or_zero(mc_market_border.total_id_flow, time)
                rows.append(
                    {
                        "Name": market_border_name,
                        "TimeStep": time,
                        "MaximumFlow": value_or_zero(mc_market_border.maximum_flow, time),
                        "MinimumFlow": value_or_zero(mc_market_border.minimum_flow, time),
                        "TotalFlow": total_flow,
                        "TotalIDFlow": value_or_zero(mc_market_border.total_id_flow, time),
                    }
                )
        return build_rows_dataframe(rows, schema)

    def create_rr_borders_data(self) -> pl.DataFrame:
        schema = {
            "Name": pl.Utf8,
            "TimeStep": pl.Datetime(time_zone="UTC"),
            "MaximumFlow": pl.Float64,
            "MinimumFlow": pl.Float64,
            "TotalFlow": pl.Float64,
            "RRActivated": pl.Float64,
        }
        rows = []
        for market_border_name, mc_market_border in self.input_dataset.mc_market_borders.items():
            for time in self.input_dataset.times:
                total_flow = value_or_zero(mc_market_border.da_flow, time)
                total_flow += value_or_zero(mc_market_border.total_id_flow, time)
                total_flow += value_or_zero(mc_market_border.rr_activated, time)
                rows.append(
                    {
                        "Name": market_border_name,
                        "TimeStep": time,
                        "MaximumFlow": value_or_zero(mc_market_border.maximum_flow, time),
                        "MinimumFlow": value_or_zero(mc_market_border.minimum_flow, time),
                        "TotalFlow": total_flow,
                        "RRActivated": value_or_zero(mc_market_border.rr_activated, time),
                    }
                )
        return build_rows_dataframe(rows, schema)

    def create_mfrr_borders_data(self) -> pl.DataFrame:
        schema = {
            "Name": pl.Utf8,
            "TimeStep": pl.Datetime(time_zone="UTC"),
            "MaximumFlow": pl.Float64,
            "MinimumFlow": pl.Float64,
            "TotalFlow": pl.Float64,
            "MFRRActivated": pl.Float64,
        }
        rows = []
        for market_border_name, mc_market_border in self.input_dataset.mc_market_borders.items():
            for time in self.input_dataset.times:
                total_flow = value_or_zero(mc_market_border.da_flow, time)
                total_flow += value_or_zero(mc_market_border.total_id_flow, time)
                total_flow += value_or_zero(mc_market_border.rr_activated, time)
                total_flow += value_or_zero(mc_market_border.mfrr_activated, time)
                rows.append(
                    {
                        "Name": market_border_name,
                        "TimeStep": time,
                        "MaximumFlow": value_or_zero(mc_market_border.maximum_flow, time),
                        "MinimumFlow": value_or_zero(mc_market_border.minimum_flow, time),
                        "TotalFlow": total_flow,
                        "MFRRActivated": value_or_zero(mc_market_border.mfrr_activated, time),
                    }
                )
        return build_rows_dataframe(rows, schema)
