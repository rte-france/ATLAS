"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import itertools
import math
from collections.abc import Callable

from pendulum import DateTime

import atlas.config as cfg
from atlas import OrderCoupling, ScenarioMatrix, SolverOptions, Thermal
from atlas.enum import CouplingType, ThermalStrategy
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.dao_output_dataset import DayAheadOrdersOutputDataset
from atlas.modules.day_ahead_orders.dao_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.orders_formulation.thermal import (
    combination_1,
    combination_2,
    combination_3,
    combination_4,
    combination_5,
    combination_6,
    combination_7,
    combination_8,
)
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_optimization_model import (
    ThermalOptimizationModel,
)
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_unit_orders import ThermalUnitOrders


class ThermalIntermediateLoadOrders(ThermalUnitOrders):
    def __init__(
        self, dataset: DayAheadOrdersOutputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ):
        super().__init__(dataset, orders_time, parameters)

    def formulate_thermal_intermediate_load_orders(self) -> None:
        """
        This function formulates orders for the thermic intermediate load units.
        Intermediate load units are identified from an attribute of the thermic class.

        Returns None
        """

        # Filter the intermediate load instances
        equipments_list = [eqt for eqt in self.dataset.thermal if eqt.strategy == ThermalStrategy.INTERMEDIATE]

        # We stop here if there is no intermediate load units in the dataset
        if not equipments_list:
            cfg.logger.info("No intermediate load units were found in the dataset.")
            return None

        # Solve the optimisation programs
        res = self.solve_optimization_programs(equipments_list)

        for thermal_unit in equipments_list:
            # Consider the unique cases
            cases = self.get_unique_cases(res, thermal_unit)

            # Create a list that will all online time frames across all scenarios
            online_timeframes = []
            for case in cases:
                # Encode the outcome as a state sequence
                states_sequence = self.determine_intermediate_load_states_sequence(thermal_unit, res, case)

                # Extract the list of online time frames
                list_of_online_timeframes = self.extract_online_sequences(states_sequence, case)

                # Formulate the orders over each online timeframe.
                for online_timeframe in list_of_online_timeframes:
                    online_timeframes.append(online_timeframe)  # Add the time frame to the list of time frames
                    self.formulate_unit_orders(online_timeframe, thermal_unit, case=case)

            # Formulate the exclusion links between scenarios
            # Consider only the time frames that are overlapping
            overlapping_blocks = self.get_overlapping_timeframes(online_timeframes)

            if overlapping_blocks:
                # Retrieve the orders corresponding to the first order of each time frame
                # time frames are mutually exclusive provided that the unit's minimum power is not null
                # over the whole orders time sequence
                if sum(thermal_unit.minimum_power.get_value(t) for t in self.orders_time) > 0.0:
                    # Create a list of order names to retrieve.
                    orders_names = []
                    for block in overlapping_blocks:
                        # Get the two start dates of the colliding blocks and their names (i.e. cases)
                        start_date_order_1, start_date_order_2 = block[0].first_date(), block[1].first_date()
                        case_order_1, case_order_2 = block[0].name, block[1].name
                        orders_names.append(
                            f"order_at_{start_date_order_1}_for_unit_{thermal_unit.name}_under_price_{case_order_1}"
                        )
                        orders_names.append(
                            f"order_at_{start_date_order_2}_for_unit_{thermal_unit.name}_under_price_{case_order_2}"
                        )

                    # Filter the orders to keep only those with the relevant name.
                    orders_list = [order for order in self.dataset.order if order.name in orders_names]

                    # Now that we recovered the orders, filter them by case and generate the exclusion links
                    # across orders of different scenarios.
                    sorted_orders = []  # Create a list of lists, each list contains orders attached to the same case
                    for case in cases:
                        current_case = []
                        for order in orders_list:
                            if case in order.name:
                                current_case.append(order)
                        sorted_orders.append(current_case)

                    for cases_pairs in itertools.combinations(
                        sorted_orders, 2
                    ):  # Consider pairwise combination across cases
                        exclusion_combinations = list(
                            itertools.product(cases_pairs[0], cases_pairs[1])
                        )  # Compute all unique pairs across the two lists, i.e. across the orders
                        # attached to case i and those attached to case j for (i,j) two cases
                        # belonging to the set of all cases.
                        for exclusion_combination in exclusion_combinations:  # Create the exclusion links between cases
                            # Unwrap the two orders
                            order_1, order_2 = exclusion_combination[0], exclusion_combination[1]
                            # Create the coupling and add the two orders.
                            coupling = OrderCoupling(
                                name=f"EXCLUSION_link_between_orders_{order_1.name}_and_{order_2.name}",
                                coupling_type=CouplingType.EXCLUSION,
                                orders=[],
                            )
                            coupling.orders.append(order_1)
                            coupling.orders.append(order_2)
                            self.dataset.order_coupling.append(coupling)

    def get_unique_cases(self, results: dict[str, dict[str, Timeseries]], thermal_unit: Thermal) -> list[str]:
        """
        Returns a list of unique cases for the associated thermal unit.

        For instance, if there are three cases Low, Medium and High and that the outcomes under cases Medium and High
        are identical, then cases = ["Low", "Medium"]

        Arguments:
        `results` : the dictionary of results
        `thermal_unit`the unit from which the results need to be retrieved

        Returns:
        cases : a list of cases names (string) each of which is unique.
        """

        # Quick sanity check on the class of the equipment supplied as input.
        if not isinstance(thermal_unit, Thermal):
            cfg.logger.error(f"*** WARNING ***\n Equipement {thermal_unit.name} is not of type thermic.")
            raise ValueError("Wrong equipment type for the thermic optimization program.")

        # extract the list of scenarios.
        scenarios_names = results[thermal_unit.name].keys()

        # See whether the unit has a minimum_stable_power_duration
        has_flat = (
            True
            if min(thermal_unit.minimum_stable_power_duration.total_hours(), thermal_unit.minimum_time_on.total_hours())
            >= 2
            else False
        )

        # For each price curve, we collapse all ON states. This is why we needed to know whether the unit has
        # two or three ON states. Due to the mutual exclusion constraint, the resulting serie will take values in {0,1} only.

        # initialize the list of collapsed outcomes
        collapsed_outcomes = []

        # consider the two possible cases
        if has_flat:
            for case in scenarios_names:
                # Aggregate the three ON states
                isOn_time_serie = (
                    results[thermal_unit.name][case]["ON_UP"]
                    + results[thermal_unit.name][case]["ON_DOWN"]
                    + results[thermal_unit.name][case]["ON_FLAT"]
                )
        else:
            for case in scenarios_names:
                # Aggregate the two ON states
                isOn_time_serie = (
                    results[thermal_unit.name][case]["ON_UP"] + results[thermal_unit.name][case]["ON_DOWN"]
                )
        # Set the name of the new time serie, corresponds to the name of the case under consideration.
        isOn_time_serie.name = case
        # Add this time serie to the list
        collapsed_outcomes.append(isOn_time_serie)

        # Now based on the collapsed time series, we are able to do pairwise comparisons across all scenarios and determine whether two of them
        # are overlapping or not.

        # list of scenarios to be discarded (if already marked as overlapping)
        to_discard = []
        for pair in itertools.combinations(collapsed_outcomes, 2):
            if self.is_overlapping(pair):
                # add the first scenario (arbitrarily) to the list of scenarios to be discarded if
                # the current scenario pair is perfectly overlapping
                to_discard.append(pair[0])

        # Remove scenarios to be discarded from the initial list. By construction, at least one scenario
        # will not be discarded.
        for scenario in to_discard:
            collapsed_outcomes.remove(scenario)

        if not collapsed_outcomes:  # If all scenarios are removed (i.e. all identical)
            # arbitrarily add one scenario to collapsed_outcomes
            collapsed_outcomes = [to_discard[0]]

        # Keep the name of the unique scenarios only.
        cases = [item.name for item in collapsed_outcomes]

        return cases

    def determine_intermediate_load_states_sequence(
        self, unit: Thermal, res: dict[str, dict[str, Timeseries]], case: str
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

        Arguments :
        `unit`: the unit to be analysed
        `res` : the dictionary of results
        `case` : a string corresponding to the name of the scenario

        Returns :
        states_sequence : a timeSeries object encoding the states at each time t.
        """

        # Compute T_stable, T_start and T_stop : will be used to see which states will be incorporated
        T_start = int(math.floor(unit.startup_duration / self.parameters.time_step))
        T_stop = int(math.floor(unit.shutdown_duration / self.parameters.time_step))
        T_stable = int(math.ceil(unit.minimum_stable_power_duration / self.parameters.time_step))

        # Since states are mutually exclusive, we need to sum them in order to collapse them on a single time series.

        # Baseline : the unit is OFF or ON_UP (or ON_DOWN)
        # Multiply OFF by 0 because this state is encoded as 0 in the states_sequence
        states_sequence = (
            res[unit.name][case]["OFF"].__mul__(0.0) + res[unit.name][case]["ON_UP"] + res[unit.name][case]["ON_DOWN"]
        )

        # Now add the conditional states if relevant :
        if min(T_stable, int(unit.minimum_time_on.total_hours())) >= 2:
            states_sequence += res[unit.name][case]["ON_FLAT"]

        if T_start > 0:
            # Encoded as 2 in states_sequence.
            states_sequence += res[unit.name][case]["START"].__mul__(2.0)

        if T_stop > 0:
            # Encoded as 3 in states_sequence
            states_sequence += res[unit.name][case]["STOP"].__mul__(3.0)

        # Edit the states_sequence properties
        states_sequence.name = f"states sequence for unit {unit.name} under scenario {case}"

        return states_sequence

    def get_overlapping_timeframes(self, online_timeframes: list[Timeseries]) -> list[tuple[Timeseries]]:
        """
        Given a list of timeframes, returns the subset of overlapping timeframes.

        Argument:
        `online_timeframes` : a list of time frames.

        Return :
        `overlapping_blocks` : a list of tuples of overlapping blocks
        """
        # Initialize the output
        overlapping_blocks: list[tuple[Timeseries]] = []

        # Test the potential overlaps
        for pair in itertools.combinations(online_timeframes, 2):
            # Unwrap the start date and end dates of the pairs
            name_pair_1, name_pair_2 = pair[0].name, pair[1].name
            start_pair_1, end_pair_1 = pair[0].first_date(), pair[0].last_date()
            start_pair_2, end_pair_2 = pair[1].first_date(), pair[1].last_date()

            # Test whether the dates are overlapping or not.
            is_overlapping = False
            if name_pair_1 != name_pair_2:
                if start_pair_1 <= start_pair_2 <= end_pair_1 or start_pair_2 <= start_pair_1 <= end_pair_2:
                    is_overlapping = True

            # Save the first dates of the colliding blocks.
            if is_overlapping:
                # Add the tuple containing the two colliding blocks.
                overlapping_blocks.append(pair)

        return overlapping_blocks

    def is_overlapping(self, pair) -> bool:
        """
        checks whether two optimization program outcomes are overlapping or not
        Compares series containing status variables only, more precisely aggregated ON status variables.

        Arguments:
        - pair : a tuple of scenarios of size 2

        Returns :
        - is_overlapping : a boolean indicating whether the scenarios are overlapping or not.
        """

        # Quick sanity check on the length of the input variable.
        if not len(pair) == 2:
            raise ValueError("The pair inputed in the is_overlapping function has not a length of 2.")

        # Extract both scenarios
        scenario_1, scenario_2 = pair[0], pair[1]

        # by default, we assume that both scenarios perfectly overlap
        # to verify this, we see whether the difference across all time steps is 0
        # if there exist one t such that the difference is not null, then scenarios are
        # not perfectly overlapping
        is_overlapping = True
        # check each element of the time serie
        for t in scenario_1.index():
            # We are comparing integer values only, so no need to round the comparison
            if scenario_1.get_value(t) != scenario_2.get_value(t):
                is_overlapping = False

        return is_overlapping

    def solve_optimization_programs(self, equipments_list: Thermal) -> dict[str, dict[str, Timeseries]]:
        """
        Solves the optimization programs for a list of equipment given the three price curves.

        Arguments:
        equiment_list : a list of thermal equipments

        Returns:
        results : a two stage dictionary containing for each equipment the optimal quantities given a price curve.
        """

        # create a dictionary that will store the program's outcomes.
        results: dict[str, dict[str, Timeseries]] = {}

        solver_options = SolverOptions(
            presolve=self.parameters.use_presolve,
            duality_gap=self.parameters.solver_duality_gap,
            time_limit=self.parameters.solver_time_out,
        )

        for unit in equipments_list:
            # Initialize a key with the unit's name.
            results[unit.name] = {}

            # Retrieve the price forecasts types, extract the corresponding time series and store it in a list
            price_types: list[str] = self.parameters.price_forecasts_types
            prices: list[Timeseries] = []

            for price_type in price_types:
                if price_type == "Low":
                    prices_low = unit.portfolio.market_area.price_forecast_low.get_forecast(
                        self.parameters.execution_date,
                        self.parameters.start_date,
                        self.parameters.end_optimization_date,
                    )
                    prices.append(prices_low)

                elif price_type == "Medium":
                    prices_medium = unit.portfolio.market_area.price_forecast_medium.get_forecast(
                        self.parameters.execution_date,
                        self.parameters.start_date,
                        self.parameters.end_optimization_date,
                    )
                    prices.append(prices_medium)

                elif price_type == "High":
                    prices_high = unit.portfolio.market_area.price_forecast_high.get_forecast(
                        self.parameters.execution_date,
                        self.parameters.start_date,
                        self.parameters.end_optimization_date,
                    )
                    prices.append(prices_high)

                else:
                    cfg.logger.error(
                        "WARNING: Wrong PriceForecastsType indicated as parameters. \n"
                        "Possible values are: 'Low', 'Medium', 'High'"
                    )

            # Initialize the output of the function

            # Solve three times the optimization program, one for each price curve
            # and store the optimal output quantities into the dictionaries
            for price, value in zip(prices, price_types, strict=False):
                model = ThermalOptimizationModel(self.parameters, unit, price, value, solver_options)
                model.create_objective_function("maximize")
                combination_functions: dict[int, Callable[..., None]] = {
                    1: combination_1.execute,
                    2: combination_2.execute,
                    3: combination_3.execute,
                    4: combination_4.execute,
                    5: combination_5.execute,
                    6: combination_6.execute,
                    7: combination_7.execute,
                    8: combination_8.execute,
                }
                combination_function = combination_functions.get(model.determine_combination(), combination_1.execute)
                day_zero = model.is_day_zero()
                combination_function(model=model, day_zero=day_zero)

                res = model.solve_thermal_optimization()
                results[unit.name][value] = res

                # Store state sequences in the output marker
                local_time_index = res["OFF"].index

                new_sequence_ts = Timeseries.from_index(
                    self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
                )

                for time in local_time_index:
                    if res["ON_UP"].get_value(time) == 1:
                        new_sequence_ts.set_value(time, 1)
                        continue

                    if res["ON_DOWN"].get_value(time) == 1:
                        new_sequence_ts.set_value(time, 2)
                        continue

                    if res["OFF"].get_value(time) == 1:
                        new_sequence_ts.set_value(time, 3)
                        continue

                    if "START" in res.keys():
                        if res["START"].get_value(time) == 1:
                            new_sequence_ts.set_value(time, 4)
                            continue

                    if "STOP" in res.keys():
                        if res["STOP"].get_value(time) == 1:
                            new_sequence_ts.set_value(time, 5)
                            continue

                    if "ON_FLAT" in res.keys():
                        if res["ON_FLAT"].get_value(time) == 1:
                            new_sequence_ts.set_value(time, 6)
                            continue

                if unit.state_sequence is None:
                    unit.state_sequence = ScenarioMatrix()
                unit.state_sequence.add(new_sequence_ts, f"{self.parameters.execution_date}-{value.upper()}_DAO")

        return results
