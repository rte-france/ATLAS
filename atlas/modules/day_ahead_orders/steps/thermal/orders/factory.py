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


_TIME_FORMAT = "DD_MM_YYYY_HH_mm_ss"


def _format_t(t: DateTime) -> str:
    return t.format(_TIME_FORMAT)


def _with_price_suffix(scenario_name: str | None) -> str:
    """
    Build the ``_with_price[...]`` order-name suffix used by base/intermediate strategies.

    ``None`` returns ``""`` — used by the peak strategy, which has no price scenario.
    """
    if scenario_name is None:
        return ""
    if scenario_name == "":
        return "_with_price"
    return f"_with_price_{scenario_name}"


def _under_price_suffix(case: str) -> str:
    """Suffix variant used by inflexible Pmin orders: ``_under_price`` or ``_under_price_{case}``."""
    return f"_under_price_{case}" if case else "_under_price"


class ThermalOrderFactory:
    """
    Static factory for Day-Ahead thermal order creation.

    All methods produce sell orders on the DayAhead product with ``is_agent_tso=False``.
    Time formatting and scenario suffixes are derived internally from ``t`` and
    ``scenario_name`` — callers no longer pass pre-formatted strings.
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
        scenario_name: str | None = None,
    ) -> OrderDAO:
        return ThermalOrderFactory._base(
            name=f"flexible_order_at_{_format_t(t)}_for_unit_{unit.name}{_with_price_suffix(scenario_name)}",
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
        scenario_name: str | None = None,
    ) -> OrderDAO:
        """
        :param direction: ``"upward"`` or ``"downward"``
        :param reserve_type: ``"automated"`` or ``"manual"``
        :param proportional_penalty: Fraction applied to qmin (``1 - proportional_reserves_penalty``)
        :param scenario_name: ``None`` for peak (no suffix); ``""`` or ``"<case>"`` for base/intermediate.
        """
        sign = 1 if direction == "upward" else -1
        return ThermalOrderFactory._base(
            name=(
                f"{reserve_type}_{direction}_reserve_order_at_{_format_t(t)}_for_unit_"
                f"{unit.name}{_with_price_suffix(scenario_name)}"
            ),
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
        scenario_name: str = "",
    ) -> OrderDAO:
        """Startup ramp order. Only emitted by base/intermediate strategies."""
        return ThermalOrderFactory._base(
            name=f"startup_ramp_order_at_{t}_for_unit_{unit.name}{_with_price_suffix(scenario_name)}",
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
        scenario_name: str = "",
    ) -> OrderDAO:
        """Shutdown ramp order. Only emitted by base/intermediate strategies."""
        return ThermalOrderFactory._base(
            name=f"shutdown_ramp_order_at_{t}_for_unit_{unit.name}{_with_price_suffix(scenario_name)}",
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
        case: str = "",
    ) -> OrderDAO:
        """Inflexible Pmin order for base/intermediate strategies. Suffix uses ``_under_price``."""
        return ThermalOrderFactory._base(
            name=f"order_at_{_format_t(t)}_for_unit_{unit.name}{_under_price_suffix(case)}",
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
    ) -> OrderDAO:
        """Inflexible Pmin order for peak strategy. No scenario suffix."""
        return ThermalOrderFactory._base(
            name=f"inflexible_order_at_{_format_t(t)}_for_unit_{unit.name}",
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
        t: DateTime,
        scenario_name: str | None = None,
    ) -> OrderCouplingDAO:
        return OrderCouplingDAO(
            name=(
                f"parent_children_inflexible_flexible_orders_at_{_format_t(t)}_for_unit_"
                f"{unit_name}{_with_price_suffix(scenario_name)}"
            ),
            coupling_type=CouplingType.PARENT_CHILDREN,
            orders=[inflexible, child],
        )

    @staticmethod
    def identical_ratio(
        inflexible_orders: list[OrderDAO],
        unit_name: str,
        start_t: DateTime,
        scenario_name: str = "",
    ) -> OrderCouplingDAO:
        return OrderCouplingDAO(
            name=(
                f"identical_ratio_inflexible_orders_for_unit_{unit_name}_starting_at_"
                f"{_format_t(start_t)}{_with_price_suffix(scenario_name)}"
            ),
            coupling_type=CouplingType.IDENTICAL_RATIO,
            orders=inflexible_orders,  # type: ignore[arg-type]
        )
