"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas import Thermal, Timeseries
from atlas.enums import CouplingType, Product, ThermalStrategy
from atlas.models.market.order import Order
from atlas.modules.day_ahead_orders.dao_timeseries import DAOTimeseries
from atlas.modules.day_ahead_orders.data_models.order import OrderDAO
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_base_load_orders import ThermalBaseLoadOrders
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_intermediate_load_orders import (
    ThermalIntermediateLoadOrders,
)
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_peak_load_orders import ThermalPeakLoadOrders
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters

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

# New improved structure of this file for clarity, organized as follows:
# . Main function, calling order formulation functions for each strategy
# . Orders formulation per strategy
# . Function formulating orders for each individual units (used for Baseload and Intermediate strategies)
# . Functions used to identify unique cases amongst High, Low and Medium Priceforecasts scenarios
# . Functions used to extract sequences and states


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
        :return: None
        """

        # Formulate baseload orders
        cfg.logger.info("Formulation of the thermic baseload orders...")
        thermal_base_load_orders = ThermalBaseLoadOrders(self.dataset, self.orders_time, self.parameters)
        thermal_base_load_orders.formulate_thermal_baseload_orders()

        # Formulate intermediate load orders
        cfg.logger.info(
            "Baseload orders formulation completed. Moving on to the formulation of the intermediate load orders..."
        )
        thermal_intermediate_load_orders = ThermalIntermediateLoadOrders(
            self.dataset, self.orders_time, self.parameters
        )
        thermal_intermediate_load_orders.formulate_thermal_intermediate_load_orders()

        # Formulate peak load orders
        cfg.logger.info(
            "Intermediate load orders formulation completed. Moving on to the formulation of the peak load orders..."
        )

        thermal_peak_load_orders = ThermalPeakLoadOrders(self.dataset, self.orders_time, self.parameters)
        thermal_peak_load_orders.formulate_thermal_peak_load_orders()
        cfg.logger.info("Peak load orders formulation completed.")

        # This is done last and not during the bidding process because of mutually exclusive programs, and to simplify debug
        cfg.logger.info("Computing maximum sell volumes...")
        self.computeDASellSubmittedVolumes()
        cfg.logger.info("End of computation.")

    def computeDASellSubmittedVolumes(self) -> None:
        """
        compute DA sell submitted volumes
        :return: None
        """
        da_sell_submitted_volumes = {
            equipment.name: DAOTimeseries(
                Timeseries.from_index(
                    self.parameters.start_date, self.parameters.timestep, self.parameters.end_date, default_value=0
                )
            )
            for equipment in self.dataset.thermal
        }

        # Getting only relevant orders
        list_of_relevant_orders_intermediate: list[OrderDAO] = []
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
                    list_of_relevant_orders_intermediate.append(order)

        # --- Intermediate ---
        # Creation of a reversed dict of all coupling in which a given order is involved
        unit_order_coupling_list: dict[str, Coupling] = {}
        for coupling_instance in self.dataset.order_coupling:
            for order_index, order_from_coupling in enumerate(coupling_instance.orders):
                if order_from_coupling in list_of_relevant_orders_intermediate:
                    if coupling_instance.coupling_type == CouplingType.EXCLUSION:
                        others = [o for o in coupling_instance.orders if o is not order_from_coupling]
                        new_coupling = Coupling(others, CouplingType.EXCLUSION)
                    elif coupling_instance.coupling_type == CouplingType.PARENT_CHILDREN:
                        if order_index == 0:
                            # order is parent
                            new_coupling = Coupling(coupling_instance.orders[1:], "PARENT")
                        else:
                            # order is child
                            new_coupling = Coupling([coupling_instance.orders[0]], "CHILD")
                    elif coupling_instance.coupling_type == CouplingType.IDENTICAL_VOLUME:
                        others = [o for o in coupling_instance.orders if o is not order_from_coupling]
                        new_coupling = Coupling(others, CouplingType.IDENTICAL_VOLUME)
                    else:
                        cfg.logger.warning(
                            "COMPLEMENT are not supposed to be connected by EXCLUSION couplings and are ignored"
                        )
                        break

                    if order_from_coupling.name not in unit_order_coupling_list:
                        unit_order_coupling_list[order_from_coupling.name] = Coupling([])

                    unit_order_coupling_list[order_from_coupling.name] = new_coupling

        # This stored already considered orders to prevent double counting
        # We use a dict to access elements using hashing to improve compute time
        already_considered_orders = {order.name: False for order in list_of_relevant_orders_intermediate}
        list_of_mutually_exclusive_programms: dict[str, list[Timeseries]] = {
            equipment.name: [] for equipment in self.dataset.thermal
        }

        for coupling_instance in self.dataset.order_coupling:
            if coupling_instance.coupling_type != CouplingType.EXCLUSION:
                continue

            for coupled_order in coupling_instance.orders:
                if coupled_order not in list_of_relevant_orders_intermediate:
                    continue
                if not already_considered_orders[coupled_order.name]:
                    programm, list_of_considerer_orders = self.graph_search_of_connected_orders(
                        coupled_order,
                        unit_order_coupling_list,
                        DAOTimeseries(
                            Timeseries.from_index(
                                self.parameters.start_date,
                                self.parameters.timestep,
                                self.parameters.end_date,
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
        for order in list_of_relevant_orders_intermediate:
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
                        da_sell_submitted_volume.set_or_add_value(
                            t, max([programm.get_value(t) for programm in programms])
                        )
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
