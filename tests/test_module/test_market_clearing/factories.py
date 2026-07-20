"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Minimal builders for market_clearing business objects, used to assemble small synthetic
scenarios for unit-testing the phase algorithms without loading a full AtlasDataset.
"""

from pendulum import Duration
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.enums import ComplementDirection, CouplingType, OrderType, Product
from atlas.modules.market_clearing.input_objects.market_area import MarketAreaMC
from atlas.modules.market_clearing.input_objects.market_border import MarketBorderMC
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.input_objects.order_coupling import OrderCouplingMC
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market.order import Order
from atlas.objects.network_operator.control_block import ControlBlock


def make_control_block(name: str) -> ControlBlock:
    return ControlBlock(name=name)


def make_plain_market_area(name: str, control_block: ControlBlock | None = None) -> MarketArea:
    return MarketArea(name=name, control_block=control_block or make_control_block(f"cb_{name}"))


def make_market_area(
    name: str,
    control_block: ControlBlock | None = None,
    mc_orders: dict[str, OrderMC] | None = None,
    **overrides,
) -> MarketAreaMC:
    return MarketAreaMC(
        name=name,
        control_block=control_block or make_control_block(f"cb_{name}"),
        mc_orders=mc_orders or {},
        **overrides,
    )


def make_market_border(
    name: str,
    uphill_market_area: MarketAreaMC,
    downhill_market_area: MarketAreaMC,
    **overrides,
) -> MarketBorderMC:
    return MarketBorderMC(
        name=name,
        uphill_market_area=uphill_market_area,
        downhill_market_area=downhill_market_area,
        uphill_control_block=uphill_market_area.control_block,
        downhill_control_block=downhill_market_area.control_block,
        **overrides,
    )


def make_plain_order(
    name: str,
    market_area: MarketArea,
    order_type: OrderType | None = OrderType.Sell,
    price: float = 50.0,
    qmax: float = 100.0,
    qmin: float = 0.0,
    start_date: DateTime | None = None,
    end_date: DateTime | None = None,
    execution_date: DateTime | None = None,
    product: Product | None = Product.DayAhead,
    **overrides,
) -> Order:
    return Order(
        name=name,
        market_area=market_area,
        order_type=order_type,
        price=price,
        qmax=qmax,
        qmin=qmin,
        start_date=start_date,
        end_date=end_date,
        execution_date=execution_date,
        product=product,
        **overrides,
    )


def make_order(
    name: str,
    market_area: MarketArea,
    timestep: Duration,
    order_type: OrderType = OrderType.Sell,
    price: float = 50.0,
    qmax: float = 100.0,
    qmin: float = 0.0,
    start_date: DateTime | None = None,
    end_date: DateTime | None = None,
    execution_date: DateTime | None = None,
    product: Product = Product.DayAhead,
    **overrides,
) -> OrderMC:
    return OrderMC(
        name=name,
        market_area=market_area,
        order_type=order_type,
        price=price,
        qmax=qmax,
        qmin=qmin,
        start_date=start_date,
        end_date=end_date,
        execution_date=execution_date or start_date,
        product=product,
        timestep=timestep,
        **overrides,
    )


def make_order_coupling(
    name: str,
    coupling_type: CouplingType,
    orders: list[Order],
    complement_direction: ComplementDirection | None = None,
    complement_energy: float | None = None,
) -> OrderCouplingMC:
    return OrderCouplingMC(
        name=name,
        coupling_type=coupling_type,
        orders=orders,
        complement_direction=complement_direction,
        complement_energy=complement_energy,
    )
