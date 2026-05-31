"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.enums import CouplingType, OrderType, Product
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO

if TYPE_CHECKING:
    from pendulum import DateTime, Duration

    from atlas.objects.equipment.equipment import Equipment


class ThermalOrderFactory:
    """
    Static factory for Day-Ahead thermal order creation.

    Eliminates the repetitive ``OrderDAO(product=DayAhead, order_type=Sell, ...)`` boilerplate.
    All methods produce sell orders on the DayAhead product with ``is_agent_tso=False``.
    """

    @staticmethod
    def _base(
        name: str,
        unit: Equipment,
        qmax: float,
        qmin: float,
        price: float,
        t: DateTime,
        step: Duration,
        ed: DateTime,
    ) -> OrderDAO:
        portfolio = unit.portfolio if unit.portfolio is not None else None
        market_area = portfolio.market_area if portfolio is not None else None
        return OrderDAO(
            name=name,
            market_area=market_area,
            portfolio=portfolio,
            equipment=unit,
            qmax=qmax,
            qmin=qmin,
            price=price,
            product=Product.DayAhead,
            order_type=OrderType.Sell,
            is_agent_tso=False,
            execution_date=ed,  # type: ignore[arg-type]
            start_date=t,  # type: ignore[arg-type]
            end_date=t + step,  # type: ignore[arg-type]
        )

    @staticmethod
    def flexible(
        unit: Equipment,
        q_max: float,
        variable_cost: float,
        t: DateTime,
        step: Duration,
        ed: DateTime,
        formatted_t: str,
        case_suffix: str,
    ) -> OrderDAO:
        return ThermalOrderFactory._base(
            name=f"flexible_order_at_{formatted_t}_for_unit_{unit.name}{case_suffix}",
            unit=unit,
            qmax=q_max,
            qmin=0,
            price=variable_cost,
            t=t,
            step=step,
            ed=ed,
        )

    @staticmethod
    def reserve(
        unit: Equipment,
        quantity: float,
        variable_cost: float,
        penalty: float,
        direction: str,
        reserve_type: str,
        proportional_penalty: float,
        t: DateTime,
        step: Duration,
        ed: DateTime,
        formatted_t: str,
        case_suffix: str,
    ) -> OrderDAO:
        """
        :param direction: ``"upward"`` or ``"downward"``
        :param reserve_type: ``"automated"`` or ``"manual"``
        :param proportional_penalty: Fraction applied to qmin (``1 - proportional_reserves_penalty``)
        """
        sign = 1 if direction == "upward" else -1
        return ThermalOrderFactory._base(
            name=f"{reserve_type}_{direction}_reserve_order_at_{formatted_t}_for_unit_{unit.name}{case_suffix}",
            unit=unit,
            qmax=quantity,
            qmin=proportional_penalty * quantity,
            price=variable_cost + sign * penalty,
            t=t,
            step=step,
            ed=ed,
        )

    @staticmethod
    def startup_ramp(
        unit: Equipment,
        q_sell: float,
        t: DateTime,
        step: Duration,
        ed: DateTime,
        case_suffix: str,
    ) -> OrderDAO:
        return ThermalOrderFactory._base(
            name=f"startup_ramp_order_at_{t}_for_unit_{unit.name}{case_suffix}",
            unit=unit,
            qmax=q_sell,
            qmin=q_sell,
            price=unit.variable_cost.get_value(t),  # type: ignore[union-attr]
            t=t,
            step=step,
            ed=ed,
        )

    @staticmethod
    def shutdown_ramp(
        unit: Equipment,
        q_sell: float,
        t: DateTime,
        step: Duration,
        ed: DateTime,
        case_suffix: str,
    ) -> OrderDAO:
        return ThermalOrderFactory._base(
            name=f"shutdown_ramp_order_at_{t}_for_unit_{unit.name}{case_suffix}",
            unit=unit,
            qmax=q_sell,
            qmin=q_sell,
            price=round(unit.variable_cost.get_value(t), 2),  # type: ignore[union-attr]
            t=t,
            step=step,
            ed=ed,
        )

    @staticmethod
    def inflexible(
        unit: Equipment,
        min_p: float,
        variable_cost: float,
        t: DateTime,
        step: Duration,
        ed: DateTime,
        formatted_t: str,
        case: str,
    ) -> OrderDAO:
        name = (
            f"order_at_{formatted_t}_for_unit_{unit.name}_under_price_{case}"
            if case
            else f"order_at_{formatted_t}_for_unit_{unit.name}_under_price"
        )
        return ThermalOrderFactory._base(
            name=name,
            unit=unit,
            qmax=min_p,
            qmin=min_p,
            price=round(variable_cost, 2),
            t=t,
            step=step,
            ed=ed,
        )

    @staticmethod
    def peak_inflexible(
        unit: Equipment,
        min_p: float,
        price: float,
        t: DateTime,
        step: Duration,
        ed: DateTime,
        formatted_t: str,
    ) -> OrderDAO:
        return ThermalOrderFactory._base(
            name=f"inflexible_order_at_{formatted_t}_for_unit_{unit.name}",
            unit=unit,
            qmax=min_p,
            qmin=min_p,
            price=price,
            t=t,
            step=step,
            ed=ed,
        )


class ThermalCouplingFactory:
    """Static factory for Day-Ahead thermal coupling creation."""

    @staticmethod
    def parent_children(
        inflexible: OrderDAO,
        child: OrderDAO,
        unit_name: str,
        formatted_t: str,
        case_suffix: str,
    ) -> OrderCouplingDAO:
        return OrderCouplingDAO(
            name=f"parent_children_inflexible_flexible_orders_at_{formatted_t}_for_unit_{unit_name}{case_suffix}",
            coupling_type=CouplingType.PARENT_CHILDREN,
            orders=[inflexible, child],
        )

    @staticmethod
    def identical_ratio(
        inflexible_orders: list[OrderDAO],
        unit_name: str,
        start_formatted_t: str,
        case_suffix: str,
    ) -> OrderCouplingDAO:
        return OrderCouplingDAO(
            name=f"identical_ratio_inflexible_orders_for_unit_{unit_name}_starting_at_{start_formatted_t}{case_suffix}",
            coupling_type=CouplingType.IDENTICAL_RATIO,
            orders=inflexible_orders,  # type: ignore[arg-type]
        )
