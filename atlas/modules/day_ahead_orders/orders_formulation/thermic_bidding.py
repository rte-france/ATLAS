"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas import Timeseries
from atlas.enum import CouplingType, Product, ThermalStrategy
from atlas.models.market.order import Order
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.orders_formulation.thermic_base_load_orders import ThermicBaseLoadOrders
from atlas.modules.day_ahead_orders.orders_formulation.thermic_intermediate_load_orders import (
    ThermicIntermediateLoadOrders,
)
from atlas.modules.day_ahead_orders.orders_formulation.thermic_peak_load_orders import ThermicPeakLoadOrders

##### Etat des lieux au 16.10.2020 ####
#
# Base, semi base terminés
# Semi base : approfondir les tests, mais la formulation d'ordres et la formation des fenêtres
# temporelles a été testée et fonctionne.
# Les fonctions qui génèrent les états pour la semi base et celle qui crée les ordres d'exclusion semblent
# fonctionner correctement aussi.
#
# Sur le fonctionnement :
#
# startup cost : calculé dans retrieve_online_sequences, du coup détecté uniquement sur le bloc courant
# et amorti sur celui ci.
# liens d'exclusion entre les scénarios : définis entre les blocs inflexibles, donc seulement définis si la p_min est positive
# sur au moins un pas de temps.
#
# Pointe à faire

# FC: New improved structure of this file for clarity, organized as follows:
# . Main function, calling order formulation functions for each strategy
# . Orders formulation per strategy
# . Function formulating orders for each individual units (used for Baseload and Intermediate strategies)
# . Functions used to identify unique cases amongst High, Low and Medium Priceforecasts scenarios
# . Functions used to extract sequences and states


class ThermicBidding:
    # ------ Main function ------
    @staticmethod
    def formulate_thermic_orders(
        dataset: DayAheadOrdersInputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ):
        """
        This wrapper function formulates orders for all thermic units.

        Arguments:
        - `dataset`: a dataset
        - `orders_time`: a list of dates at which orders must be formulated.
        - `parameters` a named tuple of parameters, containing the common parameters.

        Returns None
        """

        # Formulate baseload orders
        cfg.logger.info("Formulation of the thermic baseload orders...")
        ThermicBaseLoadOrders.formulate_thermic_baseload_orders(dataset, orders_time, parameters)

        # Formulate intermediate load orders
        cfg.logger.info(
            "Baseload orders formulation completed. Moving on to the formulation of the intermediate load orders..."
        )
        ThermicIntermediateLoadOrders.formulate_thermic_intermediate_load_orders(dataset, orders_time, parameters)

        # Formulate peak load orders
        cfg.logger.info(
            "Intermediate load orders formulation completed. Moving on to the formulation of the peak load orders..."
        )

        ThermicPeakLoadOrders.formulate_thermic_peak_load_orders(dataset, orders_time, parameters)
        cfg.logger.info("Peak load orders formulation completed.")

        # This is done last and not during the bidding process because of mutually exclusive programs, and to simplify debug
        cfg.logger.info("Computing maximum sell volumes...")
        ThermicBidding.computeDASellSubmittedVolumes(dataset, orders_time, parameters)
        cfg.logger.info("End of computation.")

        return None

    @staticmethod
    def computeDASellSubmittedVolumes(
        dataset: DayAheadOrdersInputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ):
        da_sell_submitted_volumes = {
            equipment.name: Timeseries.from_index(
                parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
            )
            for equipment in dataset.thermal
        }

        # Getting only relevant orders
        list_of_relevant_orders_intermediate = []
        for order in dataset.order:
            if (
                order.Product == Product.DayAhead
                and type(order.equipment).__name__ == "Thermal"
                and order.start_date in orders_time
            ):
                if order.equipment.strategy == ThermalStrategy.PEAK or order.equipment.strategy == ThermalStrategy.BASE:
                    da_sell_submitted_volumes[order.equipment.name][order.start_date] += order.qmax
                else:
                    list_of_relevant_orders_intermediate.append(order)

        # --- Intermediate ---
        # Creation of a reversed dic of all coupling in which a given order is involved
        unit_order_coupling_list = {str: list}
        for coupling_instance in dataset.order_coupling:
            for order_index, order in enumerate(coupling_instance.orders):
                if order not in list_of_relevant_orders_intermediate:
                    continue

                new_coupling = []

                if coupling_instance.coupling_type == CouplingType.EXCLUSION:
                    new_coupling.append(CouplingType.EXCLUSION)
                    # We use this loop because C# does not support slices as list indexes (coupling_instance.Orders[1:] raise a type error)
                    for coupled_order_index, coupled_order in enumerate(coupling_instance.orders):
                        if coupled_order_index == order_index:
                            continue
                        new_coupling.append(coupled_order)

                elif coupling_instance.coupling_type == CouplingType.PARENT_CHILDREN:
                    new_coupling.append("PARENT")
                    if order_index == 0:
                        # order is parent
                        for coupled_order_index, coupled_order in enumerate(coupling_instance.orders):
                            if coupled_order_index == 0:
                                continue
                            new_coupling.append(coupled_order)

                    else:
                        # order is child
                        new_coupling = ["CHILD", coupling_instance.orders[0]]

                elif coupling_instance.coupling_type == CouplingType.IDENTICAL_VOLUME:
                    new_coupling.append(CouplingType.IDENTICAL_VOLUME)
                    for coupled_order_index, coupled_order in enumerate(coupling_instance.orders):
                        if coupled_order_index == order_index:
                            continue
                        new_coupling.append(coupled_order)

                else:
                    # COMPLEMENT are not supposed to be connected by EXCLUSION couplings and are ignored
                    break

                if order.name not in unit_order_coupling_list:
                    unit_order_coupling_list[order.name] = []

                unit_order_coupling_list[order.name].append(new_coupling)

                # This stored already considered orders to prevent double counting
        # We use a dic to access elements using hashing to improve compute time
        already_considered_orders = {order.name: False for order in list_of_relevant_orders_intermediate}
        list_of_mutually_exclusive_programms = {equipment.name: [] for equipment in dataset.thermal}

        for coupling_instance in dataset.order_coupling:
            if coupling_instance.coupling_type != CouplingType.EXCLUSION:
                continue

            for coupled_order in coupling_instance.orders:
                if coupled_order not in list_of_relevant_orders_intermediate:
                    continue
                if not already_considered_orders[coupled_order.name]:
                    already_considered_orders_n = []
                    programm, list_of_considerer_orders = ThermicBidding.graph_search_of_connected_orders(
                        coupled_order,
                        unit_order_coupling_list,
                        Timeseries.from_index(
                            parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
                        ),
                        already_considered_orders_n,
                    )

                    list_of_mutually_exclusive_programms[coupled_order.equipment.name].append(programm)
                    for order_name in list_of_considerer_orders:
                        already_considered_orders[order_name] = True

        # Uncoupled orders or orders coupled to non exclusive groups (COMPLEMENT for instance)
        for order in list_of_relevant_orders_intermediate:
            if not already_considered_orders[order.name]:
                da_sell_submitted_volumes[order.equipment.name][order.start_date] += order.qmax

        # --- Export ---
        for equipment in dataset.thermal:
            if equipment.strategy == ThermalStrategy.INTERMEDIATE:
                cfg.logger.warning(
                    "Warning : da_sell_submitted_volumes might not yield the correct result if several internal EXCLUSION are formulated"
                )

                da_sell_submitted_volume = da_sell_submitted_volumes[equipment.name]
                programms = list_of_mutually_exclusive_programms[equipment.name]

                if programms:
                    for t in orders_time:
                        da_sell_submitted_volume[t] += max([programm[t] for programm in programms])
                equipment.da_sell_submitted_volume = da_sell_submitted_volume

            else:
                equipment.da_sell_submitted_volume = da_sell_submitted_volumes[equipment.name]

    # This overcomplexified recursive search is used to make sure that all possible scenarios are returned in case of internal EXCLUSION couplings
    # It also prevents from double computation
    # This is valid only if at most one internal EXCLUSION order exists
    # This search might not behave correctly if one internal EXCLUSION coupling exists between two PARENTS (CHILDREN might be added)
    @staticmethod
    def graph_search_of_connected_orders(
        current_order: Order,
        unit_order_coupling_list: dict[str, list],
        current_programm: Timeseries,
        already_considered_orders_n: list,
    ):
        if current_order.name in already_considered_orders_n:  # This checks prevents cycles and ensures termination
            return current_programm, already_considered_orders_n

        # If current_order is mutually exclusive with one order of the current_programm, we ignore it
        for coupling in unit_order_coupling_list[current_order.name]:
            if coupling[0] == CouplingType.EXCLUSION:
                for coupled_order in coupling[1:]:
                    if coupled_order.name in already_considered_orders_n:
                        return current_programm, already_considered_orders_n

        # Else, we add it to the current programm
        current_programm[current_order.start_date] += current_order.qmax
        already_considered_orders_n.append(current_order.name)

        # Then, we search for connected orders
        for coupling in unit_order_coupling_list[current_order.name]:
            # Exclusion orders are already dealt with
            if coupling[0] == CouplingType.EXCLUSION:
                continue

            for coupled_order in coupling[1:]:
                if coupled_order.name not in already_considered_orders_n:
                    current_programm, already_considered_orders_n = ThermicBidding.graph_search_of_connected_orders(
                        coupled_order, unit_order_coupling_list, current_programm, already_considered_orders_n
                    )
        return current_programm, already_considered_orders_n
