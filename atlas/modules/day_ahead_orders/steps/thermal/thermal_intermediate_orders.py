"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import itertools
import math

import polars as pl
from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import CouplingType
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.thermal.thermal_optimization_model import ThermalOptimizationModel
from atlas.modules.day_ahead_orders.steps.thermal.thermal_unit_orders import ThermalUnitOrders
from atlas.objects.equipment.thermal import Thermal
from atlas.solver.models import SolverOptions


class ThermalIntermediateLoadOrders(ThermalUnitOrders):
    def __init__(self, orders_time: list[DateTime], parameters: DayAheadOrdersParameters):
        """
        :param orders_time: a list of dates over which orders will be formulated.
        :type orders_time: list[DateTime]
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        """
        super().__init__(orders_time, parameters)

    def formulate(self, unit: ThermalDAO) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        """
        This function formulates orders for a thermic intermediate load unit.

        :param unit: the thermal unit to formulate orders for
        :type unit: ThermalDAO
        :return: orders and order couplings generated for this unit
        :rtype: tuple[list[OrderDAO], list[OrderCouplingDAO]]
        """
        orders: list[OrderDAO] = []
        couplings: list[OrderCouplingDAO] = []

        # Solve the optimisation programs
        res = self.solve_optimization_programs([unit])

        # Consider the unique cases
        cases = self.get_unique_cases(res, unit)

        # Create a list that will hold all online time frames across all scenarios
        online_timeframes: list[tuple[Timeseries, str]] = []
        for case in cases:
            # Encode the outcome as a state sequence
            states_sequence = self.determine_intermediate_load_states_sequence(unit, res, case)

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

    def get_unique_cases(
        self, results: dict[str, dict[str, dict[str, Timeseries]]], thermal_unit: ThermalDAO
    ) -> list[str]:
        """
        Returns a list of unique cases for the associated thermal unit.

        For instance, if there are three cases Low, Medium and High and that the outcomes under cases Medium and High
        are identical, then cases = ["Low", "Medium"]

        :param results: the dictionary of results
        :type results: dict[str, dict[str, dict[str, Timeseries]]]
        :param thermal_unit: the unit from which the results need to be retrieved
        :type thermal_unit: ThermalDAO
        :return: a list of cases names (string) each of which is unique.
        :rtype: list[str]
        """

        # Quick sanity check on the class of the equipment supplied as input.
        if not isinstance(thermal_unit, Thermal):
            cfg.logger.error(f"Equipement {thermal_unit.name} is not of type thermic.")
            raise ValueError("Wrong equipment type for the thermic optimization program.")

        # extract the list of scenarios.
        scenarios_names = results[thermal_unit.name].keys()

        has_flat = (
            min(thermal_unit.minimum_stable_power_duration.total_hours(), thermal_unit.minimum_time_on.total_hours())
            >= 2
        )

        collapsed_outcomes: list[tuple[Timeseries, str]] = []
        for case in scenarios_names:
            unit_res = results[thermal_unit.name][case]
            is_on = unit_res["ON_UP"] + unit_res["ON_DOWN"]
            if has_flat:
                is_on += unit_res["ON_FLAT"]
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

    def determine_intermediate_load_states_sequence(
        self, unit: ThermalDAO, res: dict[str, dict[str, dict[str, Timeseries]]], case: str
    ) -> Timeseries:
        """
        Computes the sequence of states on a single time frame for the intermediate load unit passed as input.
        It computes the state sequence for a given case (i.e. price scenario)

        The encoding of the states is the following:
        - 0 if the unit is offline at t
        - 1 if the unit is online at t
        - 2 if the unit is in its start up phase at t
        - 3 if the unit is in its shutdown phase at t

        The sequence of states is computed over the timeFrame

        :param unit: the unit to be analyzed
        :type unit: ThermalDAO
        :param res: the dictionary of results
        :type res: dict[str, dict[str, dict[str, Timeseries]]]
        :param case: a string corresponding to the name of the scenario
        :type case: str
        :return: a timeSeries object encoding the states at each time t.
        :rtype: Timeseries

        """

        # Compute T_stable, T_start and T_stop : will be used to see which states will be incorporated
        T_start = int(math.floor(unit.startup_duration / self.parameters.temporal.timestep))
        T_stop = int(math.floor(unit.shutdown_duration / self.parameters.temporal.timestep))
        T_stable = int(math.ceil(unit.minimum_stable_power_duration / self.parameters.temporal.timestep))

        # Since states are mutually exclusive, we need to sum them in order to collapse them on a single time series.

        # Baseline : the unit is OFF or ON_UP (or ON_DOWN)
        # Multiply OFF by 0 because this state is encoded as 0 in the states_sequence
        states_sequence = (
            res[unit.name][case]["OFF"] * 0.0 + res[unit.name][case]["ON_UP"] + res[unit.name][case]["ON_DOWN"]
        )

        # Now add the conditional states if relevant :
        if min(T_stable, int(unit.minimum_time_on.total_hours())) >= 2:
            states_sequence += res[unit.name][case]["ON_FLAT"]

        if T_start > 0:
            # Encoded as 2 in states_sequence.
            states_sequence += res[unit.name][case]["START"] * 2.0

        if T_stop > 0:
            # Encoded as 3 in states_sequence
            states_sequence += res[unit.name][case]["STOP"] * 3.0

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

    def _load_price_forecast(self, unit: ThermalDAO, price_type: str) -> Timeseries:
        attr_name = f"price_forecast_{price_type.lower()}"
        forecast = getattr(unit.portfolio.market_area, attr_name)
        if forecast is None:
            raise AttributeError(f"{unit.portfolio.market_area.name} has no attribute '{attr_name}'")
        return forecast.get_forecast(
            self.parameters.temporal.execution_date,
            self.parameters.temporal.start_date,
            self.parameters.temporal.end_date + unit.additional_hours,
        )

    def _build_state_sequence(self, res: dict[str, Timeseries]) -> Timeseries:
        tz = self.parameters.temporal.start_date.timezone_name
        local_time_index = list(res["OFF"].index)

        values = []
        for time in local_time_index:
            if "ON_UP" in res and res["ON_UP"].get_value(time) == 1:
                values.append(1)
                continue
            if "ON_DOWN" in res and res["ON_DOWN"].get_value(time) == 1:
                values.append(2)
                continue
            if "OFF" in res and res["OFF"].get_value(time) == 1:
                values.append(3)
                continue
            if "START" in res and res["START"].get_value(time) == 1:
                values.append(4)
                continue
            if "STOP" in res and res["STOP"].get_value(time) == 1:
                values.append(5)
                continue
            if "ON_FLAT" in res and res["ON_FLAT"].get_value(time) == 1:
                values.append(6)
                continue
            values.append(0)

        return Timeseries(
            pl.DataFrame(
                {"time": local_time_index, "value": values},
                schema={"time": pl.Datetime("us", tz), "value": pl.Float64()},
            )
        )

    def solve_optimization_programs(
        self, equipments_list: list[ThermalDAO]
    ) -> dict[str, dict[str, dict[str, Timeseries]]]:
        """
        Solves the optimization programs for a list of equipment given the three price curves.

        :param equipments_list: a list of thermal equipments
        :type equipments_list: list[ThermalDAO]
        :return: a two stage dictionary containing for each equipment the optimal quantities given a price curve.
        :rtype: dict[str, dict[str, dict[str, Timeseries]]]
        """
        results: dict[str, dict[str, dict[str, Timeseries]]] = {}
        solver_options = SolverOptions(
            presolve=self.parameters.solver.use_presolve,
            duality_gap=self.parameters.solver.duality_gap,
            time_limit=self.parameters.solver.timeout,
        )

        for unit in equipments_list:
            results[unit.name] = {}
            price_types: list[str] = self.parameters.price_forecasts_types

            for price_type in price_types:
                price = self._load_price_forecast(unit, price_type)
                model = ThermalOptimizationModel(self.parameters, unit, price, price_type, solver_options)
                model.add_variables()
                model.build_constraints()
                model.build_objective()

                res = model.solve_optimisation()
                results[unit.name][price_type] = res

                if unit.state_sequence is None:
                    unit.state_sequence = ScenarioMatrix()
                unit.state_sequence.add(
                    self._build_state_sequence(res),
                    f"{self.parameters.temporal.execution_date}-{price_type.upper()}_DAO",
                )

        return results
