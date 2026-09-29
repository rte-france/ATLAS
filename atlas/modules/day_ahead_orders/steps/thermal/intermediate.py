"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import itertools

import polars as pl
from pendulum import DateTime

from atlas.enums import CouplingType
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.thermal.optimisation import ThermalOptimisationResult
from atlas.modules.day_ahead_orders.steps.thermal.orders import ThermalUnitOrders


class ThermalIntermediateLoadOrders(ThermalUnitOrders):
    def __init__(self, orders_time: list[DateTime], parameters: DayAheadOrdersParameters):
        """
        :param orders_time: a list of dates over which orders will be formulated.
        :type orders_time: list[DateTime]
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        """
        super().__init__(orders_time, parameters)

    def formulate(
        self, unit: ThermalDAO, results: dict[str, ThermalOptimisationResult]
    ) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        """
        This function formulates orders for a thermic intermediate load unit.

        :param unit: the thermal unit to formulate orders for
        :type unit: ThermalDAO
        :param results: the solved optimisation programs of the unit, keyed by price scenario
        :type results: dict[str, ThermalOptimisationResult]
        :return: orders and order couplings generated for this unit
        :rtype: tuple[list[OrderDAO], list[OrderCouplingDAO]]
        """
        orders: list[OrderDAO] = []
        couplings: list[OrderCouplingDAO] = []

        # Consider the unique cases
        cases = self.get_unique_cases(results)

        # Create a list that will hold all online time frames across all scenarios
        online_timeframes: list[tuple[Timeseries, str]] = []
        for case in cases:
            # Encode the outcome as a state sequence
            states_sequence = self.determine_intermediate_load_states_sequence(results[case])

            # Extract the list of online time frames
            list_of_online_timeframes = self.extract_online_sequences(states_sequence, case)

            # Formulate the orders over each online timeframe.
            for online_timeframe, case_name in list_of_online_timeframes:
                online_timeframes.append((online_timeframe, case_name))
                unit_orders, unit_couplings = self.formulate_unit_orders(online_timeframe, unit, case=case_name)
                orders.extend(unit_orders)
                couplings.extend(unit_couplings)

        # Formulate the exclusion links between scenarios
        # Consider only the time frames that are overlapping
        overlapping_blocks = self.get_overlapping_timeframes(online_timeframes)

        if overlapping_blocks:
            # time frames are mutually exclusive provided that the unit's minimum power is not null
            if unit.minimum_power.timeseries.filter(pl.col("time").is_in(self.orders_time))["value"].sum() > 0.0:
                orders_names = [
                    f"order_at_{ts.first_date()}_for_unit_{unit.name}_under_price_{case}"
                    for (ts, case), _ in overlapping_blocks
                ] + [
                    f"order_at_{ts.first_date()}_for_unit_{unit.name}_under_price_{case}"
                    for _, (ts, case) in overlapping_blocks
                ]
                orders_list = [order for order in orders if order.name in orders_names]
                sorted_orders = [[o for o in orders_list if case in o.name] for case in cases]

                for orders_a, orders_b in itertools.combinations(sorted_orders, 2):
                    for order_1, order_2 in itertools.product(orders_a, orders_b):
                        couplings.append(
                            OrderCouplingDAO(
                                name=f"EXCLUSION_link_between_orders_{order_1.name}_and_{order_2.name}",
                                coupling_type=CouplingType.EXCLUSION,
                                orders=[order_1, order_2],  # type: ignore [arg-type]
                            )
                        )

        return orders, couplings

    def get_unique_cases(self, results: dict[str, ThermalOptimisationResult]) -> list[str]:
        """
        Returns a list of unique cases for the associated thermal unit.

        For instance, if there are three cases Low, Medium and High and that the outcomes under cases Medium and High
        are identical, then cases = ["Low", "Medium"]

        :param results: the solved optimisation programs of the unit, keyed by price scenario
        :type results: dict[str, ThermalOptimisationResult]
        :return: a list of cases names (string) each of which is unique.
        :rtype: list[str]
        """
        collapsed_outcomes: list[tuple[Timeseries, str]] = []
        for case, result in results.items():
            is_on = result.on_up + result.on_down
            if result.on_flat is not None:
                is_on += result.on_flat
            collapsed_outcomes.append((is_on, case))

        # Now based on the collapsed time series, we are able to do pairwise comparisons across all scenarios and determine whether two of them
        # are overlapping or not.

        # list of scenarios to be discarded (if already marked as overlapping)
        to_discard: list[tuple[Timeseries, str]] = []
        for pair in itertools.combinations(collapsed_outcomes, 2):
            if self.is_overlapping((pair[0][0], pair[1][0])):
                # add the first scenario (arbitrarily) to the list of scenarios to be discarded if
                # the current scenario pair is perfectly overlapping
                to_discard.append(pair[0])

        # Remove scenarios to be discarded from the initial list. By construction, at least one scenario
        # will not be discarded.
        for scenario in to_discard:
            collapsed_outcomes.remove(scenario)

        if len(collapsed_outcomes) == 0 and len(to_discard) > 0:  # If all scenarios are removed (i.e. all identical)
            # arbitrarily add one scenario to collapsed_outcomes
            collapsed_outcomes = [to_discard[0]]

        # Keep the name of the unique scenarios only.
        cases: list[str] = [case_name for _, case_name in collapsed_outcomes]

        return cases

    def determine_intermediate_load_states_sequence(self, result: ThermalOptimisationResult) -> Timeseries:
        """
        Computes the sequence of states on a single time frame for the intermediate load unit passed as input.
        It computes the state sequence for a given case (i.e. price scenario)

        The encoding of the states is the following:
        - 0 if the unit is offline at t
        - 1 if the unit is online at t
        - 2 if the unit is in its start up phase at t
        - 3 if the unit is in its shutdown phase at t

        Which conditional states exist is read off the result itself: ``start``, ``stop`` and
        ``on_flat`` are only set when the unit has the corresponding phase.

        :param result: the solved optimisation program of the unit for one price scenario
        :type result: ThermalOptimisationResult
        :return: a timeSeries object encoding the states at each time t.
        :rtype: Timeseries
        """
        # Since states are mutually exclusive, we need to sum them in order to collapse them on a single time series.

        # Baseline : the unit is OFF or ON_UP (or ON_DOWN)
        # Multiply OFF by 0 because this state is encoded as 0 in the states_sequence
        states_sequence = result.off * 0.0 + result.on_up + result.on_down

        # Now add the conditional states if relevant :
        if result.on_flat is not None:
            states_sequence += result.on_flat
        if result.start is not None:
            # Encoded as 2 in states_sequence.
            states_sequence += result.start * 2.0
        if result.stop is not None:
            # Encoded as 3 in states_sequence
            states_sequence += result.stop * 3.0

        return states_sequence

    def get_overlapping_timeframes(
        self, online_timeframes: list[tuple[Timeseries, str]]
    ) -> list[tuple[tuple[Timeseries, str], tuple[Timeseries, str]]]:
        """
        Given a list of timeframes, returns the subset of overlapping timeframes.

        :param online_timeframes: a list of time frames with their case names.
        :type online_timeframes: list[tuple[Timeseries, str]]
        :return: a list of tuples of overlapping blocks
        :rtype: list[tuple[tuple[Timeseries, str], tuple[Timeseries, str]]]
        """
        overlapping_blocks: list[tuple[tuple[Timeseries, str], tuple[Timeseries, str]]] = []
        for pair in itertools.combinations(online_timeframes, 2):
            (ts1, name1), (ts2, name2) = pair
            if name1 == name2:
                continue
            s1, e1 = ts1.first_date(), ts1.last_date()
            s2, e2 = ts2.first_date(), ts2.last_date()
            if s1 <= s2 <= e1 or s2 <= s1 <= e2:
                overlapping_blocks.append(pair)
        return overlapping_blocks

    def is_overlapping(self, pair: tuple[Timeseries, Timeseries]) -> bool:
        """
        checks whether two optimization program outcomes are overlapping or not
        Compares series containing status variables only, more precisely aggregated ON status variables.

        :param pair: a tuple of scenarios of size 2
        :type pair: tuple[Timeseries, Timeseries]
        :return: a boolean indicating whether the scenarios are overlapping or not.
        :rtype: bool
        """

        if not len(pair) == 2:
            raise ValueError("The pair inputed in the is_overlapping function has not a length of 2.")

        scenario_1, scenario_2 = pair[0], pair[1]
        # by default, we assume that both scenarios perfectly overlap
        # to verify this, we see whether the difference across all time steps is 0
        # if there exist one t such that the difference is not null, then scenarios are not perfectly overlapping
        return scenario_1 == scenario_2
