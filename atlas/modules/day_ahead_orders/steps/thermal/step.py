"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import traceback
from collections import defaultdict

import atlas.config as cfg
from atlas.enums import CouplingType, Product, ThermalStrategy
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractOrderStep, StepResult
from atlas.modules.day_ahead_orders.steps.thermal.base import ThermalBaseLoadOrders
from atlas.modules.day_ahead_orders.steps.thermal.intermediate import ThermalIntermediateLoadOrders
from atlas.modules.day_ahead_orders.steps.thermal.optimisation import (
    ThermalOptimisationResult,
    build_dispatch_state_sequence,
    solve_thermal_unit,
)
from atlas.modules.day_ahead_orders.steps.thermal.peak import ThermalPeakLoadOrders
from atlas.objects.equipment.thermal import Thermal
from atlas.objects.market.order import Order

SolvedScenarios = dict[str, ThermalOptimisationResult]


def optimize_single_thermal_unit(
    thermal: ThermalDAO,
    parameters: DayAheadOrdersParameters,
) -> SolvedScenarios | None:
    """
    Solve the bidding model of one thermal unit, once per price scenario.

    Runs either in a worker process or in the main process, depending on the
    multiprocessing parameters — hence the raw solved states as a return value rather than
    orders, which would drag the whole equipment graph through pickle.

    Only intermediate-load units are optimised: base and peak strategies derive their
    orders from the unit's own availability, with no LP involved.

    :param thermal: Thermal unit to optimise
    :type thermal: ThermalDAO
    :param parameters: Order formulation parameters
    :type parameters: DayAheadOrdersParameters
    :return: Solved states keyed by price scenario, or ``None`` when the unit needs no
        optimisation or the solve failed
    :rtype: SolvedScenarios | None
    """
    if thermal.strategy != ThermalStrategy.INTERMEDIATE:
        return None

    try:
        cfg.logger.debug(f"Optimizing thermal unit {thermal.name}")
        return {
            price_type: solve_thermal_unit(thermal, parameters, price_type)
            for price_type in parameters.price_forecasts_types
        }
    except Exception as e:
        cfg.logger.error(f"Optimization failed for thermal unit {thermal.name}: {e}")
        cfg.logger.info(traceback.format_exc())
        return None


class Coupling:
    def __init__(self, orders: list[Order], coupling_type: str = ""):
        self.coupling_type = coupling_type
        self.orders = orders


class ThermalBiddingStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
        result = StepResult()

        for thermal, solved in self.run_units(
            self.dataset.thermal,
            optimize_single_thermal_unit,
            self.parameters,
            label="thermal",
        ):
            orders, couplings = self._build_orders(thermal, solved)
            result.orders.extend(orders)
            result.order_couplings.extend(couplings)

        cfg.logger.info("Computing maximum sell volumes...")
        self._compute_da_sell_submitted_volume(result)
        cfg.logger.info("End of computation.")

        return result

    def _build_orders(
        self, thermal: ThermalDAO, solved: SolvedScenarios | None
    ) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        """
        Formulate the orders of one unit according to its strategy.

        A unit whose formulation raises is logged and skipped, so that one inconsistent
        unit does not cost the whole session.
        """
        try:
            orders, couplings = self._formulate_strategy(thermal, solved)
        except Exception as e:
            cfg.logger.error(f"Order formulation failed for thermal unit {thermal.name}: {e}")
            cfg.logger.info(traceback.format_exc())
            return [], []

        cfg.logger.info(f"Completed order formulation for thermal unit: {thermal.name} ({thermal.strategy})")
        return orders, couplings

    def _formulate_strategy(
        self, thermal: ThermalDAO, solved: SolvedScenarios | None
    ) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        if thermal.strategy == ThermalStrategy.BASE:
            return ThermalBaseLoadOrders(self.orders_time, self.parameters).formulate(thermal)

        if thermal.strategy == ThermalStrategy.PEAK:
            return ThermalPeakLoadOrders(self.orders_time, self.parameters).formulate(thermal)

        if thermal.strategy == ThermalStrategy.INTERMEDIATE:
            if solved is None:
                cfg.logger.warning(f"Order formulation failed for thermal unit: {thermal.name}")
                return [], []
            self._store_state_sequences(thermal, solved)
            return ThermalIntermediateLoadOrders(self.orders_time, self.parameters).formulate(thermal, solved)

        cfg.logger.warning(f"Unknown thermal strategy {thermal.strategy} for unit {thermal.name}")
        return [], []

    def _store_state_sequences(self, thermal: ThermalDAO, solved: SolvedScenarios) -> None:
        """Record the solved dispatch of every scenario on the unit, for downstream modules."""
        if thermal.state_sequence is None:
            thermal.state_sequence = ScenarioMatrix()
        for price_type, unit_result in solved.items():
            thermal.state_sequence.add(
                build_dispatch_state_sequence(unit_result, self.parameters),
                f"{self.parameters.temporal.execution_date}-{price_type.upper()}_DAO",
            )

    def _compute_da_sell_submitted_volume(self, result: StepResult) -> None:
        sell_submitted_volumes: dict[str, Timeseries] = {
            equipment.name: Timeseries.from_index(
                self.parameters.temporal.start_date,
                self.parameters.temporal.timestep,
                self.parameters.temporal.end_date,
                default_value=0,
            )
            for equipment in self.dataset.thermal
        }

        relevent_orders_intermediate: list[OrderDAO] = []
        relevant_orders_names: set[str] = set()

        for order in result.orders:
            if (
                order.product == Product.DayAhead
                and isinstance(order.equipment, Thermal)
                and order.start_date in self.orders_time
            ):
                if order.equipment.strategy == ThermalStrategy.PEAK or order.equipment.strategy == ThermalStrategy.BASE:
                    if order.start_date in sell_submitted_volumes[order.equipment.name]:
                        sell_submitted_volumes[order.equipment.name].set_value(
                            order.start_date, order.qmax if order.qmax is not None else 0
                        )
                    else:
                        sell_submitted_volumes[order.equipment.name].add_index(
                            order.start_date, order.qmax if order.qmax is not None else 0
                        )
                else:
                    relevent_orders_intermediate.append(order)
                    relevant_orders_names.add(order.name)

        unit_order_coupling_list: dict[str, Coupling] = defaultdict(lambda: Coupling([]))
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
                    cfg.logger.warning(
                        "COMPLEMENT are not supposed to be connected by EXCLUSION couplings and are ignored"
                    )
                    break

                unit_order_coupling_list[order_from_coupling.name] = new_coupling

        already_considered_orders = {order.name: False for order in relevent_orders_intermediate}
        list_of_mutually_exclusive_programms: dict[str, list[Timeseries]] = {
            equipment.name: [] for equipment in self.dataset.thermal
        }

        for coupling_instance in result.order_couplings:
            if coupling_instance.coupling_type != CouplingType.EXCLUSION:
                continue

            for coupled_order in coupling_instance.orders:
                if coupled_order.name not in relevant_orders_names:
                    continue
                if not already_considered_orders[coupled_order.name]:
                    programm, list_of_considerer_orders = self.graph_search_of_connected_orders(
                        coupled_order,
                        unit_order_coupling_list,
                        Timeseries.from_index(
                            self.parameters.temporal.start_date,
                            self.parameters.temporal.timestep,
                            self.parameters.temporal.end_date,
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
                if order.start_date in sell_submitted_volumes[order.equipment.name]:
                    sell_submitted_volumes[order.equipment.name].set_value(
                        order.start_date, order.qmax if order.qmax is not None else 0
                    )
                else:
                    sell_submitted_volumes[order.equipment.name].add_index(
                        order.start_date, order.qmax if order.qmax is not None else 0
                    )

        for equipment in self.dataset.thermal:
            if equipment.strategy == ThermalStrategy.INTERMEDIATE:
                cfg.logger.warning(
                    "Warning : sell_submitted_volumes might not yield the correct result if several internal EXCLUSION are formulated"
                )

                sell_submitted_volume: Timeseries = sell_submitted_volumes[equipment.name]
                programms: list[Timeseries] = list_of_mutually_exclusive_programms[equipment.name]

                if programms:
                    for t in self.orders_time:
                        max_val = max((programm.get_value(t) for programm in programms), default=0)
                        if t in sell_submitted_volume:
                            sell_submitted_volume.set_value(t, max_val)
                        else:
                            sell_submitted_volume.add_index(t, max_val)

                if equipment.da_sell_submitted_volume is None:
                    equipment.da_sell_submitted_volume = sell_submitted_volume
                else:
                    equipment.da_sell_submitted_volume = equipment.da_sell_submitted_volume.add_on_union(
                        sell_submitted_volume, inplace=False
                    )

            else:
                if equipment.da_sell_submitted_volume is None:
                    equipment.da_sell_submitted_volume = sell_submitted_volumes[equipment.name]
                else:
                    equipment.da_sell_submitted_volume = equipment.da_sell_submitted_volume.add_on_union(
                        sell_submitted_volumes[equipment.name], inplace=False
                    )

    def graph_search_of_connected_orders(
        self,
        current_order: Order,
        unit_order_coupling_list: dict[str, Coupling],
        current_programm: Timeseries,
        already_considered_orders_n: list[str],
    ) -> tuple[Timeseries, list[str]]:
        """
        Recursive search to find all possible scenarios in case of internal EXCLUSION couplings.
        Valid only if at most one internal EXCLUSION order exists.
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
                    current_programm, already_considered_orders_n = self.graph_search_of_connected_orders(
                        coupled_order, unit_order_coupling_list, current_programm, already_considered_orders_n
                    )
        return current_programm, already_considered_orders_n
