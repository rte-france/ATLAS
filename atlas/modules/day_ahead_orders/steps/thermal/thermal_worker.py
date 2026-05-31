"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import ThermalStrategy
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.thermal.intermediate_orders import ThermalIntermediateLoadOrders
from atlas.modules.day_ahead_orders.steps.thermal.optimisation_result import ThermalOptimisationResult


def optimize_single_thermal_unit(
    thermal: ThermalDAO,
    orders_time: list[DateTime],
    parameters: DayAheadOrdersParameters,
) -> dict[str, ThermalOptimisationResult] | None:
    """
    Worker function for thermal unit LP solve (INTERMEDIATE strategy only).

    Runs the LP via :class:`ThermalIntermediateLoadOrders` and returns raw results
    keyed by price type. Returns ``None`` for BASE and PEAK strategies — their
    heuristics run directly in the main process.

    :param thermal: Thermal unit to optimise.
    :param orders_time: List of datetimes for order formulation.
    :param parameters: Order formulation parameters.
    :return: LP outputs keyed by price type, or ``None`` for rule-based strategies.
    """
    try:
        cfg.logger.debug(f"Formulating orders for thermal unit {thermal.name} with strategy {thermal.strategy}")

        if thermal.strategy == ThermalStrategy.INTERMEDIATE:
            return ThermalIntermediateLoadOrders(orders_time, parameters).solve(thermal)

        if thermal.strategy in (ThermalStrategy.BASE, ThermalStrategy.PEAK):
            return None

        cfg.logger.warning(f"Unknown thermal strategy {thermal.strategy} for unit {thermal.name}")
        return None

    except Exception as e:
        cfg.logger.error(f"Order formulation failed for thermal unit {thermal.name}: {e}")
        import traceback

        cfg.logger.info(traceback.format_exc())
        return None
