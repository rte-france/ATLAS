"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math

import pendulum
from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas import Thermal, generate_datetimes
from atlas.enum import ThermalStrategy
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.dao_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.dao_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_unit_orders import ThermalUnitOrders


class ThermalBaseLoadOrders:
    # ------ Order formulation for each strategy ------
    # Base
    @staticmethod
    def formulate_thermal_baseload_orders(
        dataset: DayAheadOrdersInputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ) -> None:
        """
        This function formulates offers for the thermic baseload units.
        Baseload units are identified thanks to an attribute of the thermic class.

        Arguments:
        - `dataset`: a dataset
        - `orders_time`: a list of dates at which orders must be formulated.
        - `parameters` a named tuple of parameters, containing the common parameters.

        Returns None
        """

        # Filter the baseload instances
        equipments_list = [eqt for eqt in dataset.thermal if eqt.strategy == ThermalStrategy.BASE]

        # We stop here if there is no baseload load units in the dataset
        if not equipments_list:
            cfg.logger.info("No baseload units were found in the dataset.")
            return None

        # Start the formulation of the orders
        for unit in equipments_list:
            # Get the states sequence and the inconsistency status of the unit.
            states_sequence, inconsistent = ThermalBaseLoadOrders.determine_baseload_states_sequence(unit, parameters)
            if inconsistent:  # skip the unit if its states sequence is inconsistent.
                cfg.logger.warning(
                    f"*** WARNING ***\n Equipment {unit.name}'s states sequence is inconsistent. "
                    "No orders have been formulated for this unit"
                )
                continue

            # Retrieve the time steps over which the unit is oneline.
            list_of_online_timeframes = ThermalBaseLoadOrders.extract_online_sequences(
                states_sequence, orders_time, parameters
            )

            # Formulate the orders over each online timeframe.
            for online_timeframe in list_of_online_timeframes:
                ThermalUnitOrders.formulate_unit_orders(online_timeframe, unit, orders_time, dataset, parameters)

    # ------ Sequences identification functions ------
    # These functions aim at identifying or classifying state sequences of a unit
    @staticmethod
    def determine_baseload_states_sequence(
        unit: Thermal, parameters: DayAheadOrdersParameters
    ) -> tuple[Timeseries, bool]:
        """
        Computes the sequence of states on a single time frame for the baseload unit passed as input.

        The encoding of the states is the following:
        - 0 if the unit is offline at t
        - 1 if the unit is online at t
        - 2 if the unit is in its start up phase at t
        - 3 if the unit is in its shutdown phase at t

        The sequence of states is computed over the extended time frame, retrieved with the input parameters.
        For the baseload unit, the extentedTimeFrame corresponds to start_date - T_traceback * time_step , ... , end_date + T_traceback * time_step

        REMARK : if there are more than one start up and one shutdown over the period, the program will be considered as inconsistent.

        Arguments :
        unit : the unit to be analysed
        parameters : the signed tuple of parameters.

        Returns :
        states_sequence : a timeSeries object encoding the states at each time t.
        inconsistent : a boolean indicating whether the reconstructed time series exhibits any inconsistency
                       with respect to the unit's parameters.
        """

        # Intialize the value of the boolean inconsistent
        inconsistent = False

        # Sanity check : see whether the unit passed as an input is a baselaod unit
        # Otherwise raise an error.
        if not unit.strategy == ThermalStrategy.BASE:
            cfg.logger.error(f"*** WARNING ***\n Equipement {unit.name} is not of strategy 'Base'.")
            raise ValueError("Wrong equipment type for the thermic optimization program.")

        # Parameters from the unit
        T_on = int(max(1, math.ceil(unit.minimum_time_on / parameters.time_step)))
        T_off = int(max(1, math.ceil(unit.minimum_time_off / parameters.time_step)))
        T_start = int(math.floor(unit.startup_duration / parameters.time_step))
        T_stop = int(math.floor(unit.shutdown_duration / parameters.time_step))

        # MaximumPower of the unit
        maximum_power = unit.maximum_power

        # Compute T_traceback
        T_traceback = int(max(T_on + T_start, T_off + T_stop)) + 1

        # extended_start_date and extended_end_date
        extended_start_date = parameters.start_date - T_traceback * parameters.time_step
        extended_end_date = parameters.end_date - T_traceback * parameters.time_step

        # extended_time_frame
        extended_time_frame = generate_datetimes(extended_start_date, extended_end_date, parameters.time_step)

        # Initialize the output time series
        states_sequence = Timeseries.from_index(
            start_date=extended_start_date, frequency=parameters.time_step, end_date=extended_end_date, default_value=0
        )

        # Iterate trough the unit's maximum_power and based on the current value, determine whether the unit
        for t in extended_time_frame:
            if t in maximum_power and maximum_power.get_value(t) > 0:
                states_sequence.set_value(t, 1)

        # See if there is only one startup or shutdown over the time frame. If it is not the case, the program will be considered as
        # inconsistent.
        startup_count, shutdown_count = 0, 0
        for t in extended_time_frame[1:]:
            t_prev = t - parameters.time_step
            if states_sequence.get_value(t) - states_sequence.get_value(t_prev) == 1:
                startup_count += 1
            elif states_sequence.get_value(t_prev) - states_sequence.get_value(t) == 1:
                shutdown_count += 1

        # If there is more than one start up or one shutdown, the sequence is considered as inconsistent.
        if startup_count > 1 or shutdown_count > 1:
            inconsistent = True
            return states_sequence, inconsistent

        # Reconstruction of the start ups and the shutdown phases
        if T_start > 0 or T_stop > 0:  # Do this only if relevant
            # Reconstruction of the start ups
            for t in extended_time_frame[1:]:
                t_prev = t - parameters.time_step
                if states_sequence.get_value(t) - states_sequence.get_value(t_prev) == 1:
                    # Reconstruction of the start up phase which begins at t
                    started_at_t = t
                    # Determine the end of the start up phase
                    end_of_start_up = started_at_t + T_start * parameters.time_step
                    # Instanciate the startup time Frame
                    # En end is shifted of une time step because the unit ends its start-up and the beginning of the time step
                    # end_of_start_up.
                    startup_time_frame = generate_datetimes(
                        started_at_t, end_of_start_up - parameters.time_step, parameters.time_step
                    )
                    break  # Interrupt when the first startup is found.
                else:
                    startup_time_frame = []  # Create an empty startup_time_frame if no start ups are found.

            # Reconstruction of the shutdowns
            for t in extended_time_frame[1:]:
                t_prev = t - parameters.time_step
                if states_sequence.get_value(t_prev) - states_sequence.get_value(t) == 1:
                    # Reconstruction of the shutdown phase which ends at t-1
                    end_of_shutdown = t
                    # Determine the beginning of the shutdown
                    stopped_at_t = end_of_shutdown - T_stop * parameters.time_step
                    # Instanciate the shutdown time frame
                    # The beginning is shifted by one time step because the unit formally end its shutdown at the end of the
                    # time step end_of_shutdown
                    shutdown_time_frame = generate_datetimes(
                        stopped_at_t, end_of_shutdown - parameters.time_step, parameters.time_step
                    )
                    break  # Interrupt when the first startup is found.
                else:
                    shutdown_time_frame = []  # Create an empty shutdown_time_frame if no shutdowns are found.

            # Sanity checks
            if startup_time_frame and shutdown_time_frame:
                # See if the startup and shutdowns are overlapping
                overlapping_time_steps = set(startup_time_frame) & set(shutdown_time_frame)
                if overlapping_time_steps:
                    inconsistent = True
                    return states_sequence, inconsistent

                # See if the spell between the end of the start up and the beginning of the shutdown is greater than T_on
                if (end_of_shutdown - started_at_t).total_minutes() >= 0 and int(
                    math.floor((stopped_at_t - end_of_start_up) / parameters.time_step)
                ) < T_on:
                    inconsistent = True
                    return states_sequence, inconsistent
                # See if the spell between the end of the shutdown and the beginning of the shutdown is greater than T_off
                elif (end_of_shutdown - started_at_t).total_minutes() < 0 and int(
                    math.floor((started_at_t - end_of_shutdown) / parameters.time_step)
                ) < T_off:
                    inconsistent = True
                    return states_sequence, inconsistent

            # Update the values in the time series, if those values are not inconsistent
            if not inconsistent:
                if startup_time_frame:
                    for t in startup_time_frame:
                        states_sequence.set_value(t, 2)
                if shutdown_time_frame:
                    for t in shutdown_time_frame:
                        states_sequence.set_value(t, 3)

        return states_sequence, inconsistent

    @staticmethod
    def extract_online_sequences(
        states_sequence: Timeseries, orders_time: list[DateTime], parameters: DayAheadOrdersParameters, case: str = ""
    ) -> list[Timeseries]:
        """
        A helper function that extracts online sequence based on a thermal unit states sequence.

        This in particular allows for the formulation of order on several sub-intervals if the unit
        were to be restarted over the orders_time time frame.

        Arguments:
        - `unit` : the thermal unit considered
        - `states_sequence`: a time series containing the state sequence of the unit.
        - `orders_time` : an index of dates over which orders will be formulated.
        - `parameters`: a named tuple of subclass Parameters_List containing the parameters
        - `case` (optional) : a string corresponding to the name of the case under consideration. This is useful when
                               calling this function for the intermediate load and navigate across price scenarios.

        Returns:
        list_of_online_timeframes : a list of time series, each time serie containing a sequence over which the unit is online
                                empty if the unit is offline over the whole time frame
        startup : a boolean indicating whether the unit has started up or not.
        """
        # Get the time steps for which the unit is online (defined as a non-zero state):
        # Consistency of the online states wrt the minimum duration is ensured by definition of the
        # determine_baseload_states_sequence function.
        online_at_t = [pendulum.instance(dt) for dt in set(orders_time).intersection(states_sequence.index)]

        # Based on these time steps, deduce the intervals.
        # The intervals bounds are retrieved by comparing the total minutes between to time steps :
        # if the total number of minutes is greater that time_step, then the time steps i and i+1 correspond to bounds of two distinct intervals
        intervals = []
        if online_at_t:
            intervals.append(online_at_t[0])
            if len(online_at_t) >= 2:
                for i in range(len(online_at_t) - 1):
                    if not (online_at_t[i + 1] - online_at_t[i]) == parameters.time_step:
                        intervals.append(online_at_t[i])
                        intervals.append(online_at_t[i + 1])
            intervals.append(online_at_t[-1])  # Add the element. This allows for potential singletons

        # Based on the interval boundaries, retrieve the intervals
        # If the unit is online over the whole orders_time time frame, then only one interval is generated
        # Otherwise all intervals are generated, using the fact that by construction, there is an even
        # number of time steps in the intervals list.
        list_of_online_timeframes: list[Timeseries] = []
        if intervals:
            intervals.sort()
            for i in range(int(len(intervals) / 2)):
                window = states_sequence.slice(intervals[2 * i], intervals[2 * i + 1], "both", False)
                window.name = case

                # don't add duplicates
                if len(list_of_online_timeframes) == 0:
                    list_of_online_timeframes.append(window)
                elif all(window != ts for ts in list_of_online_timeframes):
                    list_of_online_timeframes.append(window)

        return list_of_online_timeframes
