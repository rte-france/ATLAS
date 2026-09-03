"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

import atlas.config as cfg
from atlas.enums import CouplingType, Product, ThermalStrategy
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractOrderStep, StepResult
from atlas.modules.day_ahead_orders.steps.thermal.thermal_worker import optimize_single_thermal_unit
from atlas.objects.equipment.thermal import Thermal
from atlas.objects.market.order import Order


class Coupling:
    def __init__(self, orders: list[Order], coupling_type: str = ""):
        self.coupling_type = coupling_type
        self.orders = orders


class ThermalBiddingStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
        if self.parameters.multiprocessing.enable:
            result = self._formulate_parallel()
        else:
            result = self._formulate_sequential()

        cfg.logger.info("Computing maximum sell volumes...")
        self._compute_da_sell_submitted_volume(result)
        cfg.logger.info("End of computation.")

        return result

    def _formulate_parallel(self) -> StepResult:
        cfg.logger.info(f"Starting parallel thermal optimization for {len(self.dataset.thermal)} units")
        result = StepResult()

        with ProcessPoolExecutor(max_workers=self.parameters.multiprocessing.max_workers) as executor:
            future_to_thermal = {
                executor.submit(optimize_single_thermal_unit, thermal, self.orders_time, self.parameters): thermal.name
                for thermal in self.dataset.thermal
            }

            for future in as_completed(future_to_thermal):
                thermal_name = future_to_thermal[future]
                try:
                    unit_result = future.result()

                    if unit_result.success:
                        result.orders.extend(unit_result.orders)
                        result.order_couplings.extend(unit_result.order_couplings)
                        cfg.logger.info(
                            f"Completed order formulation for thermal unit: {thermal_name} ({unit_result.strategy.value})"
                        )
                    else:
                        cfg.logger.warning(f"Order formulation failed for thermal unit: {thermal_name}")

                except Exception as e:
                    cfg.logger.error(f"Error processing thermal unit {thermal_name}: {e}")

        return result

    def _formulate_sequential(self) -> StepResult:
        cfg.logger.info(f"Starting sequential thermal optimization for {len(self.dataset.thermal)} units")
        result = StepResult()

        for thermal in self.dataset.thermal:
            unit_result = optimize_single_thermal_unit(thermal, self.orders_time, self.parameters)

            if unit_result.success:
                result.orders.extend(unit_result.orders)
                result.order_couplings.extend(unit_result.order_couplings)
                cfg.logger.info(
                    f"Completed order formulation for thermal unit: {thermal.name} ({unit_result.strategy.value})"
                )
            else:
                cfg.logger.warning(f"Order formulation failed for thermal unit: {thermal.name}")

        return result

    def _compute_da_sell_submitted_volume(self, result: StepResult) -> None:
        da_sell_submitted_volumes: dict[str, Timeseries] = {
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
                if order.start_date in da_sell_submitted_volumes[order.equipment.name]:
                    da_sell_submitted_volumes[order.equipment.name].set_value(
                        order.start_date, order.qmax if order.qmax is not None else 0
                    )
                else:
                    da_sell_submitted_volumes[order.equipment.name].add_index(
                        order.start_date, order.qmax if order.qmax is not None else 0
                    )

        for equipment in self.dataset.thermal:
            if equipment.strategy == ThermalStrategy.INTERMEDIATE:
                cfg.logger.warning(
                    "Warning : da_sell_submitted_volumes might not yield the correct result if several internal EXCLUSION are formulated"
                )

                da_sell_submitted_volume: Timeseries = da_sell_submitted_volumes[equipment.name]
                programms: list[Timeseries] = list_of_mutually_exclusive_programms[equipment.name]

                if programms:
                    for t in self.orders_time:
                        max_val = max((programm.get_value(t) for programm in programms), default=0)
                        if t in da_sell_submitted_volume:
                            da_sell_submitted_volume.set_value(t, max_val)
                        else:
                            da_sell_submitted_volume.add_index(t, max_val)

                if equipment.da_sell_submitted_volume is None:
                    equipment.da_sell_submitted_volume = da_sell_submitted_volume
                else:
                    equipment.da_sell_submitted_volume.add_indexes(da_sell_submitted_volume)
                    equipment.da_sell_submitted_volume += da_sell_submitted_volume

            else:
                if equipment.da_sell_submitted_volume is None:
                    equipment.da_sell_submitted_volume = da_sell_submitted_volumes[equipment.name]
                else:
                    equipment.da_sell_submitted_volume.add_indexes(da_sell_submitted_volumes[equipment.name])
                    equipment.da_sell_submitted_volume += da_sell_submitted_volumes[equipment.name]

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
