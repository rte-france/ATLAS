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
from atlas.modules.day_ahead_orders.steps.thermal.optimisation_result import ThermalOptimisationResult
from atlas.modules.day_ahead_orders.steps.thermal.thermal_dao_step import ThermalDAOStep
from atlas.modules.day_ahead_orders.steps.thermal.thermal_unit_orders import ThermalUnitOrders
from atlas.objects.equipment.thermal import Thermal
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel


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
        raw = self.solve(unit)
        return self.build_orders(unit, raw)

    def solve(self, unit: ThermalDAO) -> dict[str, ThermalOptimisationResult]:
        """
        Run the LP for each price scenario and return the raw results keyed by price type.

        Also updates ``unit.state_sequence`` as a side effect.

        :param unit: Thermal unit to solve for.
        :return: LP outputs keyed by price type.
        :rtype: dict[str, ThermalOptimisationResult]
        """
        results: dict[str, ThermalOptimisationResult] = {}
        solver_options = SolverOptions(
            presolve=self.parameters.solver.use_presolve,
            duality_gap=self.parameters.solver.duality_gap,
            time_limit=self.parameters.solver.timeout,
        )

        for price_type in self.parameters.price_forecasts_types:
            price = self._load_price_forecast(unit, price_type)
            step = ThermalDAOStep(unit, price, price_type)
            model = OptimisationModel(
                self.parameters.solver.solver_name,
                f"Optimization program for thermal unit {unit.name}",
                solver_options,
            )
            step.add_variables(model, self.parameters)
            step.add_constraints(model, self.parameters)
            step.add_objective(model, self.parameters)

            if self.parameters.solver.export_lp:
                lp_dir = self.parameters.get_lp_dir()
                lp_dir.mkdir(parents=True, exist_ok=True)
                model.export_model(str(lp_dir / f"{unit.name}_price_{price_type}.lp"))

            cfg.logger.info(f"Optimisation model for '{unit.name}' with price type '{price_type}'")
            model.solve()

            raw = step.extract_result(self.parameters)
            results[price_type] = raw

            if unit.state_sequence is None:
                unit.state_sequence = ScenarioMatrix()
            unit.state_sequence.add(
                self._build_state_sequence(raw),
                f"{self.parameters.temporal.execution_date}-{price_type.upper()}_DAO",
            )

        return results

    def build_orders(
        self, unit: ThermalDAO, raw: dict[str, ThermalOptimisationResult]
    ) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        """
        Build orders and couplings from LP results for an intermediate unit.

        :param unit: Thermal unit.
        :param raw: LP outputs per price scenario, as returned by :meth:`solve`.
        :return: Orders and order couplings.
        :rtype: tuple[list[OrderDAO], list[OrderCouplingDAO]]
        """
        orders: list[OrderDAO] = []
        couplings: list[OrderCouplingDAO] = []

        cases = self.get_unique_cases(raw, unit)

        online_timeframes: list[tuple[Timeseries, str]] = []
        for case in cases:
            states_sequence = self.determine_intermediate_load_states_sequence(unit, raw, case)
            list_of_online_timeframes = self.extract_online_sequences(states_sequence, case)

            for online_timeframe, case_name in list_of_online_timeframes:
                online_timeframes.append((online_timeframe, case_name))
                unit_orders, unit_couplings = self.formulate_unit_orders(online_timeframe, unit, case=case_name)
                orders.extend(unit_orders)
                couplings.extend(unit_couplings)

        overlapping_blocks = self.get_overlapping_timeframes(online_timeframes)

        if overlapping_blocks:
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
        self, results: dict[str, ThermalOptimisationResult], thermal_unit: ThermalDAO
    ) -> list[str]:
        """
        Returns a list of unique cases for the associated thermal unit.

        For instance, if there are three cases Low, Medium and High and that the outcomes under cases Medium and High
        are identical, then cases = ["Low", "Medium"]

        :param results: LP results keyed by price type.
        :type results: dict[str, ThermalOptimisationResult]
        :param thermal_unit: the unit from which the results need to be retrieved
        :type thermal_unit: ThermalDAO
        :return: a list of cases names (string) each of which is unique.
        :rtype: list[str]
        """

        # Quick sanity check on the class of the equipment supplied as input.
        if not isinstance(thermal_unit, Thermal):
            cfg.logger.error(f"Equipement {thermal_unit.name} is not of type thermic.")
            raise ValueError("Wrong equipment type for the thermic optimization program.")

        scenarios_names = results.keys()

        has_flat = (
            min(thermal_unit.minimum_stable_power_duration.total_hours(), thermal_unit.minimum_time_on.total_hours())
            >= 2
        )

        collapsed_outcomes: list[tuple[Timeseries, str]] = []
        for case in scenarios_names:
            unit_res = results[case]
            is_on = unit_res.on_up + unit_res.on_down
            if has_flat:
                assert unit_res.on_flat is not None
                is_on += unit_res.on_flat
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
        self, unit: ThermalDAO, res: dict[str, ThermalOptimisationResult], case: str
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
        :param res: LP results keyed by price type.
        :type res: dict[str, ThermalOptimisationResult]
        :param case: a string corresponding to the name of the scenario
        :type case: str
        :return: a timeSeries object encoding the states at each time t.
        :rtype: Timeseries

        """

        T_start = int(math.floor(unit.startup_duration / self.parameters.temporal.timestep))
        T_stop = int(math.floor(unit.shutdown_duration / self.parameters.temporal.timestep))
        T_stable = int(math.ceil(unit.minimum_stable_power_duration / self.parameters.temporal.timestep))

        unit_res = res[case]
        states_sequence = unit_res.off * 0.0 + unit_res.on_up + unit_res.on_down

        if min(T_stable, int(unit.minimum_time_on.total_hours())) >= 2:
            assert unit_res.on_flat is not None
            states_sequence += unit_res.on_flat

        if T_start > 0:
            assert unit_res.start is not None
            states_sequence += unit_res.start * 2.0

        if T_stop > 0:
            assert unit_res.stop is not None
            states_sequence += unit_res.stop * 3.0

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

    def _build_state_sequence(self, res: ThermalOptimisationResult) -> Timeseries:
        tz = self.parameters.temporal.start_date.timezone_name
        local_time_index = list(res.off.index)

        values = []
        for time in local_time_index:
            if res.on_up.get_value(time) == 1:
                values.append(1)
                continue
            if res.on_down.get_value(time) == 1:
                values.append(2)
                continue
            if res.off.get_value(time) == 1:
                values.append(3)
                continue
            if res.start is not None and res.start.get_value(time) == 1:
                values.append(4)
                continue
            if res.stop is not None and res.stop.get_value(time) == 1:
                values.append(5)
                continue
            if res.on_flat is not None and res.on_flat.get_value(time) == 1:
                values.append(6)
                continue
            values.append(0)

        return Timeseries(
            pl.DataFrame(
                {"time": local_time_index, "value": values},
                schema={"time": pl.Datetime("us", tz), "value": pl.Float64()},
            )
        )
