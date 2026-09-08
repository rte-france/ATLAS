"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl
from pendulum import DateTime

from atlas.enums import ComplementDirection, CouplingType, OrderType, Product, StorageType
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.storage.storage_worker import StorageOptimisationResult


@dataclass
class StorageBids:
    """
    Everything a solved storage unit contributes to the day-ahead session.

    :param orders: Buy and sell spot orders
    :type orders: list[OrderDAO]
    :param order_couplings: Complement coupling tying those orders together
    :type order_couplings: list[OrderCouplingDAO]
    :param buy_submitted_volume: Buy volumes submitted to the market
    :type buy_submitted_volume: Timeseries
    :param sell_submitted_volume: Sell volumes submitted to the market
    :type sell_submitted_volume: Timeseries
    :param variable_cost: Variable cost derived from the bid prices
    :type variable_cost: Timeseries
    """

    orders: list[OrderDAO] = field(default_factory=list)
    order_couplings: list[OrderCouplingDAO] = field(default_factory=list)
    buy_submitted_volume: Timeseries = field(default_factory=Timeseries)
    sell_submitted_volume: Timeseries = field(default_factory=Timeseries)
    variable_cost: Timeseries = field(default_factory=Timeseries)


def build_storage_bids(
    storage: StorageDAO,
    result: StorageOptimisationResult,
    parameters: DayAheadOrdersParameters,
    local_timewindow: list[DateTime],
) -> StorageBids:
    """
    Turn the solved volumes of a storage unit into market orders.

    Runs in the main process, so the orders it creates reference the dataset's own
    equipment objects.

    :param storage: Storage unit the result belongs to
    :type storage: StorageDAO
    :param result: Solved volumes returned by the optimisation worker
    :type result: StorageOptimisationResult
    :param parameters: Module parameters
    :type parameters: DayAheadOrdersParameters
    :param local_timewindow: Timesteps of the day-ahead delivery window
    :type local_timewindow: list[DateTime]
    :return: Orders, couplings, submitted volumes and variable cost of the unit
    :rtype: StorageBids
    """
    buy_submitted_volume = Timeseries.from_values(
        parameters.temporal.start_date, parameters.temporal.timestep, list(result.buy_volumes.values())
    )
    sell_submitted_volume = Timeseries.from_values(
        parameters.temporal.start_date, parameters.temporal.timestep, list(result.sell_volumes.values())
    )

    sale_price, purchase_price = _price_calculation(storage, result, parameters)

    orders = [
        _create_spot_order(OrderType.Buy, storage, time, volume, purchase_price, parameters)
        for time, volume in result.buy_volumes.items()
    ] + [
        _create_spot_order(OrderType.Sell, storage, time, volume, sale_price, parameters)
        for time, volume in result.sell_volumes.items()
    ]

    # efficiencies are validated strictly positive on StorageDispatchInput, so no zero guard here
    variable_cost = (
        round(purchase_price, 2)
        if purchase_price != 0
        else round(sale_price * storage.discharge_efficiency * storage.charge_efficiency, 2)
    )

    return StorageBids(
        orders=orders,
        order_couplings=[
            _create_coupling(storage, result, buy_submitted_volume, sell_submitted_volume, orders, parameters)
        ],
        buy_submitted_volume=buy_submitted_volume,
        sell_submitted_volume=sell_submitted_volume,
        variable_cost=Timeseries.from_values(
            parameters.temporal.start_date,
            parameters.temporal.timestep,
            [variable_cost] * len(local_timewindow),
        ),
    )


def _price_calculation(
    storage: StorageDAO, result: StorageOptimisationResult, parameters: DayAheadOrdersParameters
) -> tuple[float, float]:
    """
    Derive the single sale and purchase price the unit bids at over the whole session.

    The unit sells at the lowest forecast price of the hours it discharges and buys at the
    highest forecast price of the hours it charges; those two are then spread symmetrically
    around the round-trip efficiency so that the arbitrage stays profitable at clearing.

    :return: (sale price, purchase price) in euros/MWh
    :rtype: tuple[float, float]
    """
    if storage.portfolio.market_area.price_forecast_medium is None:
        raise AttributeError(f"{storage.portfolio.market_area.name} has no attribute 'price_forecast_medium'")

    price_forecast = storage.portfolio.market_area.price_forecast_medium.get_forecast(
        parameters.temporal.execution_date,
        parameters.temporal.start_date,
        parameters.temporal.end_date,
        parameters.temporal.timestep,
    )

    sale_hours = [time for time, volume in result.sell_volumes.items() if volume != 0]
    purchase_hours = [time for time, volume in result.buy_volumes.items() if volume != 0]

    min_sale_price = 0.0
    max_purchase_price = 0.0
    if sale_hours:
        min_sale_price = price_forecast.dataframe.filter(pl.col("time").is_in(sale_hours)).min().select("value").item()
    if purchase_hours:
        max_purchase_price = (
            price_forecast.dataframe.filter(pl.col("time").is_in(purchase_hours)).max().select("value").item()
        )

    if storage.storage_type not in (StorageType.BATTERY, StorageType.PUMPED_HYDRAULIC_STORAGE) and not storage.is_v2g:
        # a unit that cannot discharge only ever formulates purchase orders
        return 0.0, max_purchase_price

    min_sale_price = max(min_sale_price, 0.0)
    max_purchase_price = max(max_purchase_price, 0.0)

    if not purchase_hours:
        return min_sale_price, 0.0
    if not sale_hours:
        return 0.0, max_purchase_price
    if min_sale_price == 0 and max_purchase_price == 0:
        return 0.0, 0.0

    round_trip_efficiency = storage.discharge_efficiency * storage.charge_efficiency
    spread = (round_trip_efficiency * min_sale_price - max_purchase_price) / (
        round_trip_efficiency * min_sale_price + max_purchase_price
    )
    return min_sale_price * (1 - spread), max_purchase_price * (1 + spread)


def _create_coupling(
    storage: StorageDAO,
    result: StorageOptimisationResult,
    buy_submitted_volume: Timeseries,
    sell_submitted_volume: Timeseries,
    orders: list[OrderDAO],
    parameters: DayAheadOrdersParameters,
) -> OrderCouplingDAO:
    """Create the complement coupling binding all the orders of the unit."""
    daily_buy_volume = sum(result.buy_volumes.values()) * parameters.temporal.timestep.total_hours()

    if storage.storage_type == StorageType.ELECTRIC_VEHICLE and daily_buy_volume > 0:
        assert storage.displacement_energy is not None, "displacement_energy must be set for electric vehicles"

        energy_requirement = storage.displacement_energy.get_value(
            parameters.penultimate_date
        ) - storage.displacement_energy.get_value(parameters.temporal.start_date - parameters.temporal.timestep)

        name = f"COMPLEMENT_DA_{storage.name}_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}"
        complement_energy = min(daily_buy_volume, energy_requirement)
    else:
        name = f"COMPLEMENT_DA_{storage.name}_{parameters.temporal.execution_date}"
        complement_energy = buy_submitted_volume.sum() - sell_submitted_volume.sum()

    return OrderCouplingDAO(
        name=name,
        coupling_type=CouplingType.COMPLEMENT,
        complement_direction=ComplementDirection.EqualTo,
        complement_energy=complement_energy,
        orders=orders,  # type: ignore [arg-type]
    )


def _create_spot_order(
    order_type: OrderType,
    storage: StorageDAO,
    start_date: DateTime,
    qmax: float,
    price: float,
    parameters: DayAheadOrdersParameters,
) -> OrderDAO:
    """Create a single spot order."""
    return OrderDAO(
        name=f"storage_order_type_{order_type}_at_{start_date.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{storage.name}",
        equipment=storage,
        portfolio=storage.portfolio,
        market_area=storage.portfolio.market_area,
        execution_date=parameters.temporal.execution_date,
        start_date=start_date,  # type: ignore [arg-type]
        end_date=start_date + parameters.temporal.timestep,  # type: ignore [arg-type]
        order_type=order_type,
        product=Product.DayAhead,
        qmax=qmax,
        qmin=0.0,
        price=price,
    )
