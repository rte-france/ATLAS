"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import itertools
import math

import polars as pl
from pendulum import DateTime, Duration

import atlas.config as cfg
from atlas.enums import CouplingType, OrderType, Product
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.thermal.constraint_builder import ThermalConstraintBuilder
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
        is_offline = True
        for case in cases:
            # Encode the outcome as a state sequence
            states_sequence = self.determine_intermediate_load_states_sequence(unit, res, case)

            # Extract the list of online time frames
            list_of_online_timeframes = self.extract_online_sequences(states_sequence, case)

            # Formulate the orders over each online timeframe.
            for online_timeframe, case_name in list_of_online_timeframes:
                online_timeframes.append((online_timeframe, case_name))
                unit_orders, unit_couplings = self.formulate_unit_orders(online_timeframe, unit, case=case_name)
                if unit_orders:
                    is_offline = False
                orders.extend(unit_orders)
                couplings.extend(unit_couplings)

        # Formulate the exclusion links between scenarios
        # Consider only the time frames that are overlapping
        overlapping_blocks = self.get_overlapping_timeframes(online_timeframes)

        if overlapping_blocks:
            # time frames are mutually exclusive provided that the unit's minimum power is not null
            if unit.minimum_power.timeseries.filter(pl.col("time").is_in(self.orders_time))["value"].sum() > 0.0:
                orders_by_name = {order.name: order for order in orders}
                for (ts_1, case_1), (ts_2, case_2) in overlapping_blocks:
                    order_1 = orders_by_name.get(
                        self._generic_order_name("inflexible", ts_1.first_date(), unit.name, case_1)
                    )
                    order_2 = orders_by_name.get(
                        self._generic_order_name("inflexible", ts_2.first_date(), unit.name, case_2)
                    )
                    if order_1 is not None and order_2 is not None:
                        couplings.append(
                            OrderCouplingDAO(
                                name=f"EXCLUSION_link_between_orders_{order_1.name}_and_{order_2.name}",
                                coupling_type=CouplingType.EXCLUSION,
                                orders=[order_1, order_2],  # type: ignore [arg-type]
                            )
                        )

        # If the unit failed to have any online timeframe with the standard formulation,
        # it goes through the semi-peak formulation to still generate orders
        if is_offline:
            orders, couplings = self.formulate_semi_peak(unit)

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
            cfg.logger.error(f"Equipment {thermal_unit.name} is not of type thermic.")
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

        # Now based on the collapsed time series, we are able to do pairwise
        # comparisons across all scenarios and determine whether two of them
        # are overlapping or not.

        unique_outcomes: list[tuple[Timeseries, str]] = []
        for is_on, case in collapsed_outcomes:
            if not any(self.is_overlapping((is_on, kept)) for kept, _ in unique_outcomes):
                unique_outcomes.append((is_on, case))

        return [case_name for _, case_name in unique_outcomes]

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
                model.create_objective_function("maximize")
                ThermalConstraintBuilder(model).build()

                res = model.solve_thermal_optimization()
                results[unit.name][price_type] = res

                if unit.state_sequence is None:
                    unit.state_sequence = ScenarioMatrix()
                unit.state_sequence.add(
                    self._build_state_sequence(res),
                    f"{self.parameters.temporal.execution_date}-{price_type.upper()}_DAO",
                )

        return results

    def formulate_semi_peak(self, unit: ThermalDAO) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:

        # Here, we store orders in a dict since we have to extract them later on based on their name
        orders_dict: dict[str, OrderDAO] = {}
        orders: list[OrderDAO] = []
        couplings: list[OrderCouplingDAO] = []

        # Extract relevant repeated info
        start_date = self.parameters.temporal.start_date
        end_date = self.parameters.temporal.end_date
        time_step = self.parameters.temporal.timestep

        # --- Define order durations rounded up to a whole number of time steps
        half_day = Duration(hours=12)
        full_day = Duration(hours=24)
        min_on_duration = time_step * max(1, math.ceil(unit.minimum_time_on / time_step))
        order_duration_list = sorted({min_on_duration, half_day, full_day})

        # Exclude units that are offline or with an infeasible maximum_power
        if not unit.maximum_power.index:
            cfg.logger.warning(f"Equipment {unit.name} is unavailable for semi-peak (offline).")
            return orders, couplings

        local_pmax = unit.maximum_power.filter(self.orders_time)
        local_pmin = unit.minimum_power.filter(self.orders_time)
        if (local_pmax.min() == 0) or ((local_pmax - local_pmin).min() < 0):
            cfg.logger.warning(f"Equipment {unit.name} is unavailable for semi-peak (offline).")
            return orders, couplings

        # Define if the unit was started before
        if not unit.power:
            started_before = False
        else:
            prev_power = unit.power.get_forecast(
                execution_date=self.parameters.temporal.execution_date,
                start_date=start_date - time_step,
                end_date=start_date,
                timestep=time_step,
            )
            started_before = prev_power.sum() != 0

        # --- Loop on time steps in orders_time, and formulate all orders
        for time_enum, time in enumerate(self.orders_time):
            formatted_time = time.format("DD_MM_YYYY_HH_mm_ss")

            # Inflexible order
            # ==============

            # Reads the minimum power and decides whether or not an inflexible order should be generated
            pmin_at_t = local_pmin.get_value(time)
            generate_inflex_order = pmin_at_t > 0

            if generate_inflex_order:
                # Create one inflexible order per hour, for each duration in orders_duration_list
                for order_duration in order_duration_list:
                    n_steps = int(order_duration / time_step)

                    # FC: Specific cases for 12 hours duration orders. Very simple for now,
                    # only formulated for [Oh,12h] and [12h,24h]. Could (should) be refined later on
                    if order_duration == half_day and not (time.hour in [0, 12] and time.minute == 0):
                        continue

                    # If the end date of the inflexible order is later than the considered end date,
                    # no inflexible order is created
                    if time + order_duration > end_date:
                        continue

                    # Create identical volume constraints between all the inflexible orders of a given duration
                    identical_volume_orders = []

                    for time_start in range(n_steps):
                        # Define the order price
                        price = unit.variable_cost.get_value(time + time_step * time_start)
                        if not (time_enum == 0 and started_before):
                            price += unit.startup_cost.get_value(time + time_step * time_start) / (
                                pmin_at_t * order_duration.total_hours()
                            )

                        new_order = OrderDAO(
                            name=self._semi_peak_order_name(
                                kind="inflex", n=time_start, time=time, unit_name=unit.name, duration=order_duration
                            ),
                            market_area=unit.portfolio.market_area,
                            portfolio=unit.portfolio,
                            equipment=unit,
                            qmax=pmin_at_t,
                            qmin=pmin_at_t,
                            price=round(price, 2),
                            product=Product.DayAhead,
                            order_type=OrderType.Sell,
                            is_agent_tso=False,
                            execution_date=self.parameters.temporal.execution_date,
                            start_date=time + time_step * time_start,
                            end_date=time + time_step * (time_start + 1),
                        )

                        orders_dict[new_order.name] = new_order
                        identical_volume_orders.append(new_order)

                    # Create an identical volume coupling between all orders
                    couplings.append(
                        OrderCouplingDAO(
                            name=f"IDV_inflex_semi_peak_orders_start_at_{formatted_time}"
                            f"_for_unit_{unit.name}_of_duration_{order_duration}",
                            coupling_type=CouplingType.IDENTICAL_VOLUME,
                            orders=identical_volume_orders,  # type: ignore [arg-type]
                        )
                    )

                    ### Create exclusion links with overlapping previous orders
                    # Loop over the order duration types
                    overlapping_orders: dict[Duration, list[OrderDAO]] = {}

                    for previous_order_duration in order_duration_list:
                        n_steps_prev = int(previous_order_duration / time_step)

                        if previous_order_duration not in overlapping_orders.keys():
                            overlapping_orders[previous_order_duration] = []

                        # FC: new method to create overlapping orders, to correct an error observed (empty couplings)
                        for time_diff in range(1, n_steps_prev):
                            studied_time = time - time_step * time_diff

                            if studied_time < start_date:
                                continue

                            if studied_time + previous_order_duration > end_date:
                                continue

                            wanted_name = self._semi_peak_order_name(
                                kind="inflex",
                                n=0,
                                time=studied_time,
                                unit_name=unit.name,
                                duration=previous_order_duration,
                            )

                            if wanted_name not in orders_dict.keys():
                                continue
                            local_order = orders_dict[wanted_name]

                            overlapping_orders[previous_order_duration].append(local_order)

                    # Create all exclusion links

                    current_order_name = self._semi_peak_order_name(
                        kind="inflex", n=0, time=time, unit_name=unit.name, duration=order_duration
                    )

                    current_order = orders_dict[current_order_name]

                    for previous_order_duration in overlapping_orders.keys():
                        for overlapping_order in overlapping_orders[previous_order_duration]:
                            couplings.append(
                                OrderCouplingDAO(
                                    name=f"EXCL_inflex_semi_peak_between_order_at_{overlapping_order.start_date.format('DD_MM_YYYY_HH_mm_ss')}"
                                    f"_of_duration_{previous_order_duration}_and_order_at_{formatted_time}_of"
                                    f"_duration_{order_duration.total_hours()}_for_unit_{unit.name}",
                                    coupling_type=CouplingType.EXCLUSION,
                                    orders=[current_order, overlapping_order],  # type: ignore [arg-type]
                                )
                            )

            ### Create exclusion links between the different orders starting at the same timestamp
            # Fc: Deal with potential empty couplings
            exclusion_order_list = []
            for order_duration in order_duration_list:
                # If the end date of the inflexible order is later than the considered end date,
                # no inflexible order exists so nothing is added to the exclusion list
                if time + order_duration > end_date:
                    continue

                wanted_name = self._semi_peak_order_name(
                    kind="inflex", n=0, time=time, unit_name=unit.name, duration=order_duration
                )

                if wanted_name not in orders_dict.keys():
                    continue

                added_order = orders_dict[wanted_name]

                exclusion_order_list.append(added_order)

            if exclusion_order_list:
                couplings.append(
                    OrderCouplingDAO(
                        name="EXCL_between_all_inflex_semi_peak_orders_n_0"
                        f"_starting_at_{formatted_time}_for_unit_{unit.name}",
                        coupling_type=CouplingType.EXCLUSION,
                        orders=exclusion_order_list,  # type: ignore [arg-type]
                    )
                )

            # Flexible order
            # ==============

            # Compute the maximum power of the flexible order
            q_max = unit.maximum_power.get_value(time) - unit.minimum_power.get_value(time)

            # We only formulate the order if its maximal power is positive
            if q_max <= 0.0:
                cfg.logger.info(
                    "*** WARNING ***\n No capacity available for the "
                    "flexible part of semi peak orders for "
                    f"unit {unit.name} at time {time}. The order will therefore not be created."
                )

            else:
                for order_duration in order_duration_list:
                    n_steps = int(order_duration / time_step)

                    # FC: Specific cases for 12 hours duration orders. Very simple for now,
                    # only formulated for [Oh,12h] and [12h,24h]. Could (should) be refined later on
                    if order_duration == half_day and not (time.hour in [0, 12] and time.minute == 0):
                        continue

                    # If the end date of the corresponding inflexible order is later than the considered end date, no flexible order is created
                    if time + order_duration > end_date:
                        continue

                    # Create one flexible order per hour for each duration in orders_duration_list
                    for offset_from_start in range(n_steps):
                        flexible_order = OrderDAO(
                            name=self._semi_peak_order_name(
                                kind="flex",
                                n=offset_from_start,
                                time=time,
                                unit_name=unit.name,
                                duration=order_duration,
                            ),
                            market_area=unit.portfolio.market_area,
                            portfolio=unit.portfolio,
                            equipment=unit,
                            qmax=q_max,
                            qmin=0,
                            price=round(unit.variable_cost.get_value(time + time_step * offset_from_start), 2),
                            product=Product.DayAhead,
                            order_type=OrderType.Sell,
                            is_agent_tso=False,
                            execution_date=self.parameters.temporal.execution_date,
                            start_date=time + time_step * offset_from_start,
                            end_date=time + time_step * (offset_from_start + 1),
                        )
                        orders_dict[flexible_order.name] = flexible_order

                        if generate_inflex_order:
                            inflex_name = self._semi_peak_order_name(
                                kind="inflex", n=0, time=time, unit_name=unit.name, duration=order_duration
                            )

                            # Retrieve the inflexible order
                            inflex_order = orders_dict[inflex_name]

                            # Parent-children link between the flexible and inflexible parts
                            couplings.append(
                                OrderCouplingDAO(
                                    name=f"PC_inflex_flex_orders_n_{offset_from_start}_at_{formatted_time}_"
                                    f"for_unit_{unit.name}_of_duration_{order_duration.total_hours()}",
                                    coupling_type=CouplingType.PARENT_CHILDREN,
                                    orders=[inflex_order, flexible_order],  # type: ignore [arg-type]
                                )
                            )

        return list(orders_dict.values()), couplings
