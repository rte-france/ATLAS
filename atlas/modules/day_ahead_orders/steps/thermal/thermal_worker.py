"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import ThermalStrategy
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.thermal.thermal_base_orders import ThermalBaseLoadOrders
from atlas.modules.day_ahead_orders.steps.thermal.thermal_intermediate_orders import ThermalIntermediateLoadOrders
from atlas.modules.day_ahead_orders.steps.thermal.thermal_peak_orders import ThermalPeakLoadOrders


@dataclass
class ThermalOptimizationResult:
    """
    This class stores the thermal optimization results without the unpicklable solver object,
    making it suitable for multiprocessing with ProcessPoolExecutor.

    :param thermal_name: The name of the thermal unit
    :type thermal_name: str
    :param orders: List of orders generated for this thermal unit
    :type orders: list[OrderDAO]
    :param order_couplings: List of order couplings for this thermal unit
    :type order_couplings: list[OrderCouplingDAO]
    :param success: Whether the optimization was successful
    :type success: bool
    """

    thermal_name: str
    strategy: ThermalStrategy
    orders: list[OrderDAO] = field(default_factory=list)
    order_couplings: list[OrderCouplingDAO] = field(default_factory=list)
    success: bool = True


def optimize_single_thermal_unit(
    thermal: ThermalDAO,
    orders_time: list[DateTime],
    parameters: DayAheadOrdersParameters,
) -> ThermalOptimizationResult:
    """
    Worker function for thermal unit order formulation (works for both multiprocessing and sequential).

    Formulates orders for a single thermal unit based on its strategy, then extracts results
    into a picklable ThermalOptimizationResult object (avoiding SWIG solver objects).

    :param thermal: Thermal unit to formulate orders for
    :type thermal: ThermalDAO
    :param orders_time: List of datetimes for order formulation
    :type orders_time: list[DateTime]
    :param parameters: Order formulation parameters
    :type parameters: DayAheadOrdersParameters
    :return: Thermal optimization result
    :rtype: ThermalOptimizationResult
    """
    try:
        cfg.logger.debug(f"Formulating orders for thermal unit {thermal.name} with strategy {thermal.strategy}")

        if thermal.strategy == ThermalStrategy.BASE:
            formulator = ThermalBaseLoadOrders(orders_time, parameters)
            orders, order_couplings = formulator.formulate(thermal)
        elif thermal.strategy == ThermalStrategy.INTERMEDIATE:
            formulator_inter = ThermalIntermediateLoadOrders(orders_time, parameters)
            orders, order_couplings = formulator_inter.formulate(thermal)
        elif thermal.strategy == ThermalStrategy.PEAK:
            formulator_peak = ThermalPeakLoadOrders(orders_time, parameters)
            orders, order_couplings = formulator_peak.formulate(thermal)
        else:
            cfg.logger.warning(f"Unknown thermal strategy {thermal.strategy} for unit {thermal.name}")
            return ThermalOptimizationResult(
                thermal_name=thermal.name,
                strategy=thermal.strategy or ThermalStrategy.BASE,
                success=False,
            )

        return ThermalOptimizationResult(
            thermal_name=thermal.name,
            strategy=thermal.strategy or ThermalStrategy.BASE,
            orders=orders,
            order_couplings=order_couplings,
            success=True,
        )

    except Exception as e:
        cfg.logger.error(f"Order formulation failed for thermal unit {thermal.name}: {e}")
        import traceback

        cfg.logger.debug(traceback.format_exc())
        return ThermalOptimizationResult(
            thermal_name=thermal.name,
            strategy=thermal.strategy or ThermalStrategy.BASE,
            success=False,
        )
