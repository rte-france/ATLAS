"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.enums import CouplingType, Product, ThermalStrategy
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
    from atlas.modules.day_ahead_orders.steps.result import BiddingResult
    from atlas.objects.market.order import Order


@dataclass
class Coupling:
    """Local coupling adjacency node used when building the submitted-volume graph."""

    orders: list[Order] = field(default_factory=list)
    coupling_type: str = ""


def _graph_search_of_connected_orders(
    current_order: Order,
    unit_order_coupling_list: dict[str, Coupling],
    current_programm: Timeseries,
    already_considered_orders_n: list[str],
) -> tuple[Timeseries, list[str]]:
    """
    Recursive DFS to aggregate all power volumes reachable through non-EXCLUSION couplings.

    Valid only when at most one internal EXCLUSION coupling exists per program.

    :param current_order: Entry point of the traversal
    :param unit_order_coupling_list: Per-order coupling adjacency map
    :param current_programm: Accumulator timeseries (mutated in-place during recursion)
    :param already_considered_orders_n: Visited order names (mutated in-place)
    :return: (accumulated timeseries, visited order names)
    """
    if current_order.name in already_considered_orders_n:
        return current_programm, already_considered_orders_n

    coupling = unit_order_coupling_list[current_order.name]
    if coupling.coupling_type == CouplingType.EXCLUSION:
        for coupled_order in coupling.orders:
            if coupled_order.name in already_considered_orders_n:
                return current_programm, already_considered_orders_n

    if current_order.start_date is not None:
        if current_order.start_date in current_programm:
            current_programm.set_value(
                current_order.start_date, current_order.qmax if current_order.qmax is not None else 0
            )
        else:
            current_programm.add_index(
                current_order.start_date, current_order.qmax if current_order.qmax is not None else 0
            )
    already_considered_orders_n.append(current_order.name)

    if coupling.coupling_type != CouplingType.EXCLUSION:
        for coupled_order in coupling.orders:
            if coupled_order.name not in already_considered_orders_n:
                current_programm, already_considered_orders_n = _graph_search_of_connected_orders(
                    coupled_order, unit_order_coupling_list, current_programm, already_considered_orders_n
                )
    return current_programm, already_considered_orders_n


def compute_da_sell_submitted_volume(
    result: BiddingResult,
    thermal_units: list[ThermalDAO],
    orders_time: list[DateTime],
    parameters: DayAheadOrdersParameters,
) -> dict[str, Timeseries]:
    """
    Compute the per-unit Day-Ahead sell submitted volume time series.

    For BASE and PEAK units the submitted volume is the sum of accepted sell orders.
    For INTERMEDIATE units, mutually exclusive price scenarios are detected via EXCLUSION
    couplings and only the maximum program volume per timestep is retained.

    .. warning::
        For INTERMEDIATE units, this may not yield the correct result if several
        internal EXCLUSION couplings are formulated for the same unit.

    :param result: Bidding result containing all orders and couplings.
    :param thermal_units: Thermal units to compute volumes for.
    :param orders_time: Reference timesteps for the DA market.
    :param parameters: Module parameters for temporal info.
    :return: Mapping ``equipment.name -> da_sell_submitted_volume`` timeseries.
        The caller is responsible for assigning each timeseries onto the equipment.
    """
    da_sell_submitted_volumes: dict[str, Timeseries] = {
        equipment.name: Timeseries.from_index(
            parameters.temporal.start_date,
            parameters.temporal.timestep,
            parameters.temporal.end_date,
            default_value=0,
        )
        for equipment in thermal_units
    }

    from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO

    relevent_orders_intermediate: list[OrderDAO] = []
    relevant_orders_names: set[str] = set()

    for order in result.orders:
        if (
            order.product == Product.DayAhead
            and isinstance(order.equipment, ThermalDAO)
            and order.start_date in orders_time
        ):
            if order.equipment.strategy in (ThermalStrategy.PEAK, ThermalStrategy.BASE):
                if order.start_date in da_sell_submitted_volumes[order.equipment.name]:
                    da_sell_submitted_volumes[order.equipment.name].set_value(
                        order.start_date, order.qmax if order.qmax is not None else 0
                    )
                else:
                    da_sell_submitted_volumes[order.equipment.name].add_index(
                        order.start_date, order.qmax if order.qmax is not None else 0
                    )
            else:
                relevent_orders_intermediate.append(order)
                relevant_orders_names.add(order.name)

    unit_order_coupling_list: dict[str, Coupling] = defaultdict(Coupling)
    for coupling_instance in result.order_couplings:
        coupling_type = coupling_instance.coupling_type
        orders = coupling_instance.orders

        relevant_orders_in_coupling = [o for o in orders if o.name in relevant_orders_names]
        if not relevant_orders_in_coupling:
            continue

        for order_index, order_from_coupling in enumerate(orders):
            if order_from_coupling.name not in relevant_orders_names:
                continue

            if coupling_type == CouplingType.EXCLUSION:
                others = orders[:order_index] + orders[order_index + 1 :]
                new_coupling = Coupling(others, CouplingType.EXCLUSION)
            elif coupling_type == CouplingType.PARENT_CHILDREN:
                if order_index == 0:
                    new_coupling = Coupling(orders[1:], "PARENT")
                else:
                    new_coupling = Coupling(orders[:1], "CHILD")
            elif coupling_type == CouplingType.IDENTICAL_VOLUME:
                others = orders[:order_index] + orders[order_index + 1 :]
                new_coupling = Coupling(others, CouplingType.IDENTICAL_VOLUME)
            else:
                cfg.logger.warning("COMPLEMENT are not supposed to be connected by EXCLUSION couplings and are ignored")
                break

            unit_order_coupling_list[order_from_coupling.name] = new_coupling

    already_considered_orders = {order.name: False for order in relevent_orders_intermediate}
    list_of_mutually_exclusive_programms: dict[str, list[Timeseries]] = {
        equipment.name: [] for equipment in thermal_units
    }

    for coupling_instance in result.order_couplings:
        if coupling_instance.coupling_type != CouplingType.EXCLUSION:
            continue

        for coupled_order in coupling_instance.orders:
            if coupled_order.name not in relevant_orders_names:
                continue
            if not already_considered_orders[coupled_order.name]:
                programm, list_of_considerer_orders = _graph_search_of_connected_orders(
                    coupled_order,
                    unit_order_coupling_list,
                    Timeseries.from_index(
                        parameters.temporal.start_date,
                        parameters.temporal.timestep,
                        parameters.temporal.end_date,
                        default_value=0,
                    ),
                    [],
                )

                if coupled_order.equipment is not None:
                    list_of_mutually_exclusive_programms[coupled_order.equipment.name].append(programm)
                for order_name in list_of_considerer_orders:
                    already_considered_orders[order_name] = True

    for order in relevent_orders_intermediate:
        if not already_considered_orders[order.name]:
            if order.start_date in da_sell_submitted_volumes[order.equipment.name]:
                da_sell_submitted_volumes[order.equipment.name].set_value(
                    order.start_date, order.qmax if order.qmax is not None else 0
                )
            else:
                da_sell_submitted_volumes[order.equipment.name].add_index(
                    order.start_date, order.qmax if order.qmax is not None else 0
                )

    out: dict[str, Timeseries] = {}
    for equipment in thermal_units:
        if equipment.strategy == ThermalStrategy.INTERMEDIATE:
            cfg.logger.warning(
                "Warning : da_sell_submitted_volumes might not yield the correct result if several internal EXCLUSION are formulated"
            )

            volume = da_sell_submitted_volumes[equipment.name]
            programms = list_of_mutually_exclusive_programms[equipment.name]

            if programms:
                for t in orders_time:
                    max_val = max((programm.get_value(t) for programm in programms), default=0)
                    if t in volume:
                        volume.set_value(t, max_val)
                    else:
                        volume.add_index(t, max_val)
            out[equipment.name] = volume

        else:
            out[equipment.name] = da_sell_submitted_volumes[equipment.name]

    return out
