"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

from pendulum import DateTime

import atlas.config as cfg
from atlas import Thermal, Timeseries
from atlas.enums import CouplingType, Product, ThermalStrategy
from atlas.models.market.order import Order
from atlas.modules.day_ahead_orders.dao_timeseries import DAOTimeseries
from atlas.modules.day_ahead_orders.models.order import OrderDAO
from atlas.modules.day_ahead_orders.orders_formulation.thermal_worker import optimize_single_thermal_unit
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters


class Coupling:
    def __init__(self, orders: list[Order], coupling_type: str = ""):
        self.coupling_type = coupling_type
        self.orders = orders


class ThermalBiddingStep:
    def __init__(
        self, dataset: DayAheadOrdersOutput, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ):
        """
        :param dataset: the dataset
        :type dataset: DayAheadOrdersOutput
        :param orders_time: a list of dates over which orders will be formulated.
        :type orders_time: list[DateTime]
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        """
        self.dataset = dataset
        self.orders_time = orders_time
        self.parameters = parameters

    def formulate_thermal_orders(self) -> None:
        """
        This wrapper function formulates orders for all thermic units.
        Supports both sequential and parallel processing based on use_multiprocessing parameter.
        :return: None
        """
        if self.parameters.multiprocessing.use_multiprocessing:
            self._formulate_thermal_orders_parallel()
        else:
            self._formulate_thermal_orders_sequential()

        # This is done last and not during the bidding process because of mutually exclusive programs, and to simplify debug
        cfg.logger.info("Computing maximum sell volumes...")
        self.compute_da_sell_submitted_volume()
        cfg.logger.info("End of computation.")

    def _formulate_thermal_orders_parallel(self) -> None:
        """
        Formulate thermal orders using multiprocessing for parallel execution at the unit level.
        """
        cfg.logger.info(f"Starting parallel thermal optimization for {len(self.dataset.thermal)} units")

        with ProcessPoolExecutor(max_workers=self.parameters.multiprocessing.max_workers) as executor:
            future_to_thermal = {
                executor.submit(optimize_single_thermal_unit, thermal, self.orders_time, self.parameters): thermal.name
                for thermal in self.dataset.thermal
            }

            for future in as_completed(future_to_thermal):
                thermal_name = future_to_thermal[future]
                try:
                    result = future.result()

                    if result.success:
                        # Add orders and couplings to the dataset
                        self.dataset.order.extend(result.orders)
                        self.dataset.order_coupling.extend(result.order_couplings)
                        cfg.logger.info(
                            f"Completed order formulation for thermal unit: {thermal_name} ({result.strategy.value})"
                        )
                    else:
                        cfg.logger.warning(f"Order formulation failed for thermal unit: {thermal_name}")

                except Exception as e:
                    cfg.logger.error(f"Error processing thermal unit {thermal_name}: {e}")

    def _formulate_thermal_orders_sequential(self) -> None:
        """
        Formulate thermal orders using sequential processing.
        """
        cfg.logger.info(f"Starting sequential thermal optimization for {len(self.dataset.thermal)} units")

        for thermal in self.dataset.thermal:
            result = optimize_single_thermal_unit(thermal, self.orders_time, self.parameters)

            if result.success:
                # Add orders and couplings to the dataset
                self.dataset.order.extend(result.orders)
                self.dataset.order_coupling.extend(result.order_couplings)
                cfg.logger.info(
                    f"Completed order formulation for thermal unit: {thermal.name} ({result.strategy.value})"
                )
            else:
                cfg.logger.warning(f"Order formulation failed for thermal unit: {thermal.name}")

    def compute_da_sell_submitted_volume(self) -> None:
        """
        compute DA sell submitted volumes
        :return: None
        """
        da_sell_submitted_volumes = {
            equipment.name: DAOTimeseries(
                Timeseries.from_index(
                    self.parameters.temporal.start_date,
                    self.parameters.temporal.timestep,
                    self.parameters.temporal.end_date,
                    default_value=0,
                )
            )
            for equipment in self.dataset.thermal
        }

        # Getting only relevant orders
        relevent_orders_intermediate: list[OrderDAO] = []
        relevant_orders_names: set[str] = set()  # For O(1) membership checks using order names

        for order in self.dataset.order:
            if (
                order.product == Product.DayAhead
                and isinstance(order.equipment, Thermal)
                and order.start_date in self.orders_time
            ):
                if order.equipment.strategy == ThermalStrategy.PEAK or order.equipment.strategy == ThermalStrategy.BASE:
                    da_sell_submitted_volumes[order.equipment.name].set_or_add_value(
                        order.start_date, order.qmax if order.qmax is not None else 0
                    )
                else:
                    relevent_orders_intermediate.append(order)
                    relevant_orders_names.add(order.name)

        # --- Intermediate ---
        # Creation of a reversed dict of all coupling in which a given order is involved
        # Use defaultdict to eliminate redundant key existence checks
        unit_order_coupling_list: dict[str, Coupling] = defaultdict(lambda: Coupling([]))
        for coupling_instance in self.dataset.order_coupling:
            coupling_type = coupling_instance.coupling_type
            orders = coupling_instance.orders

            # Pre-filter relevant orders to avoid redundant checks
            relevant_orders_in_coupling = [o for o in orders if o.name in relevant_orders_names]
            if not relevant_orders_in_coupling:
                continue

            for order_index, order_from_coupling in enumerate(orders):
                if order_from_coupling.name not in relevant_orders_names:
                    continue

                if coupling_type == CouplingType.EXCLUSION:
                    # Avoid list comprehension: build others list more efficiently
                    others = orders[:order_index] + orders[order_index + 1 :]
                    new_coupling = Coupling(others, CouplingType.EXCLUSION)
                elif coupling_type == CouplingType.PARENT_CHILDREN:
                    if order_index == 0:
                        # order is parent - use slice reference
                        new_coupling = Coupling(orders[1:], "PARENT")
                    else:
                        # order is child - create single-element list without comprehension
                        new_coupling = Coupling(orders[:1], "CHILD")
                elif coupling_type == CouplingType.IDENTICAL_VOLUME:
                    # Avoid list comprehension: build others list more efficiently
                    others = orders[:order_index] + orders[order_index + 1 :]
                    new_coupling = Coupling(others, CouplingType.IDENTICAL_VOLUME)
                else:
                    cfg.logger.warning(
                        "COMPLEMENT are not supposed to be connected by EXCLUSION couplings and are ignored"
                    )
                    break

                unit_order_coupling_list[order_from_coupling.name] = new_coupling

        # This stored already considered orders to prevent double counting
        # We use a dict to access elements using hashing to improve compute time
        already_considered_orders = {order.name: False for order in relevent_orders_intermediate}
        list_of_mutually_exclusive_programms: dict[str, list[Timeseries]] = {
            equipment.name: [] for equipment in self.dataset.thermal
        }

        for coupling_instance in self.dataset.order_coupling:
            if coupling_instance.coupling_type != CouplingType.EXCLUSION:
                continue

            for coupled_order in coupling_instance.orders:
                if coupled_order.name not in relevant_orders_names:
                    continue
                if not already_considered_orders[coupled_order.name]:
                    programm, list_of_considerer_orders = self.graph_search_of_connected_orders(
                        coupled_order,
                        unit_order_coupling_list,
                        DAOTimeseries(
                            Timeseries.from_index(
                                self.parameters.temporal.start_date,
                                self.parameters.temporal.timestep,
                                self.parameters.temporal.end_date,
                                default_value=0,
                            )
                        ),
                        [],
                    )

                    if coupled_order.equipment is not None:
                        list_of_mutually_exclusive_programms[coupled_order.equipment.name].append(programm)
                    for order_name in list_of_considerer_orders:
                        already_considered_orders[order_name] = True

        # Uncoupled orders or orders coupled to non-exclusive groups (COMPLEMENT for instance)
        for order in relevent_orders_intermediate:
            if not already_considered_orders[order.name]:
                da_sell_submitted_volumes[order.equipment.name].set_or_add_value(
                    order.start_date, order.qmax if order.qmax is not None else 0
                )

        # --- Export ---
        for equipment in self.dataset.thermal:
            if equipment.strategy == ThermalStrategy.INTERMEDIATE:
                cfg.logger.warning(
                    "Warning : da_sell_submitted_volumes might not yield the correct result if several internal EXCLUSION are formulated"
                )

                da_sell_submitted_volume: DAOTimeseries = da_sell_submitted_volumes[equipment.name]
                programms: list[Timeseries] = list_of_mutually_exclusive_programms[equipment.name]

                if programms:
                    for t in self.orders_time:
                        # Use generator expression instead of list comprehension for better memory efficiency
                        max_val = max((programm.get_value(t) for programm in programms), default=0)
                        da_sell_submitted_volume.set_or_add_value(t, max_val)
                equipment.da_sell_submitted_volume = da_sell_submitted_volume

            else:
                equipment.da_sell_submitted_volume = da_sell_submitted_volumes[equipment.name]

    def graph_search_of_connected_orders(
        self,
        current_order: Order,
        unit_order_coupling_list: dict[str, Coupling],
        current_programm: DAOTimeseries,
        already_considered_orders_n: list[str],
    ) -> tuple[DAOTimeseries, list[str]]:
        """
        This overcomplexified recursive search is used to make sure that all possible scenarios are returned in case of internal EXCLUSION couplings
        It also prevents from double computation
        This is valid only if at most one internal EXCLUSION order exists
        This search might not behave correctly if one internal EXCLUSION coupling exists between two PARENTS (CHILDREN might be added)

        :param current_order: the current order
        :type current_order: Order
        :param unit_order_coupling_list: a reversed dict of all coupling in which a given order is involved
        :type unit_order_coupling_list: dict[str, Coupling]
        :param current_programm: The current timeseries program
        :type current_programm: DAOTimeseries
        :param already_considered_orders_n: the list of already considered orders
        :type already_considered_orders_n: list[str]
        :return: the connected orders
        :rtype: tuple[DAOTimeseries, list[str]]
        """
        if current_order.name in already_considered_orders_n:  # This checks prevents cycles and ensures termination
            return current_programm, already_considered_orders_n

        # If current_order is mutually exclusive with one order of the current_programm, we ignore it
        coupling = unit_order_coupling_list[current_order.name]
        if coupling.coupling_type == CouplingType.EXCLUSION:
            for coupled_order in coupling.orders:
                if coupled_order.name in already_considered_orders_n:
                    return current_programm, already_considered_orders_n

        # Else, we add it to the current programm
        if current_order.start_date is not None:
            current_programm.set_or_add_value(
                current_order.start_date, current_order.qmax if current_order.qmax is not None else 0
            )
        already_considered_orders_n.append(current_order.name)

        # Then, we search for connected orders Exclusion orders are already dealt with
        if coupling.coupling_type != CouplingType.EXCLUSION:
            for coupled_order in coupling.orders:
                if coupled_order.name not in already_considered_orders_n:
                    current_programm, already_considered_orders_n = self.graph_search_of_connected_orders(
                        coupled_order, unit_order_coupling_list, current_programm, already_considered_orders_n
                    )
        return current_programm, already_considered_orders_n
