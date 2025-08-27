"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math

from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas import Order, OrderCoupling, Thermal, generate_datetimes
from atlas.enum import CouplingType, OrderType, Product, ThermalStrategy
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.tools.Utilities import Utilities

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
        ThermicBidding.formulate_thermic_baseload_orders(dataset, orders_time, parameters)

        # Formulate intermediate load orders
        cfg.logger.info(
            "Baseload orders formulation completed. Moving on to the formulation of the intermediate load orders..."
        )
        # ThermicBiding.formulate_thermic_intermediate_load_orders(dataset, orders_time, parameters)

        # Formulate peak load orders
        cfg.logger.info(
            "Intermediate load orders formulation completed. Moving on to the formulation of the peak load orders..."
        )
        # ThermicBiding.formulate_thermic_peak_load_orders(dataset, orders_time, parameters)
        cfg.logger.info("Peak load orders formulation completed.")

        # This is done last and not during the bidding process because of mutually exclusive programs, and to simplify debug
        cfg.logger.info("Computing maximum sell volumes...")
        # ThermicBiding.computeDASellSubmittedVolumes(dataset, orders_time)
        cfg.logger.info("End of computation.")

        return None

    # ------ Order formulation for each strategy ------
    # Base
    @staticmethod
    def formulate_thermic_baseload_orders(
        dataset: DayAheadOrdersInputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ):
        """
        This function formulates offers for the thermic baseload units.
        Baseload units are identified thanks to an attribute of the thermic class.

        Arguments:
        - `dataset`: a dataset
        - `orders_time`: a list of dates at which orders must be formulated.
        - `parameters` a named tuple of parameters, containing the common parameters.

        Returns None
        """

        # Get the list of Thermic instances from the input marker.
        equipments_list = dataset.thermal

        # Filter the baseload instances
        equipments_list = [eqt for eqt in equipments_list if eqt.strategy == ThermalStrategy.BASE]

        # We stop here if there is no baseload load units in the input marker
        if not equipments_list:
            cfg.logger.info("No baseload units were found in the input marker.")
            return None

        # Start the formulation of the orders
        for unit in equipments_list:
            # Get the states sequence and the inconsistency status of the unit.
            states_sequence, inconsistent = ThermicBidding.determine_baseload_states_sequence(unit, parameters)
            if inconsistent:  # skip the unit if its states sequence is inconsistent.
                cfg.logger.warning(
                    f"*** WARNING ***\n Equipment {unit.name}'s states sequence is inconsistent. "
                    "No orders have been formulated for this unit"
                )
                continue

            # Retrieve the time steps over which the unit is oneline.
            list_of_online_timeframes = ThermicBidding.extract_online_sequences(
                states_sequence, orders_time, parameters
            )

            # Formulate the orders over each online timeframe.
            for online_timeframe in list_of_online_timeframes:
                ThermicBidding.formulate_unit_orders(online_timeframe, unit, orders_time, dataset, parameters)

        return None

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
        For the baseload unit, the extentedTimeFrame corresponds to startDate - T_traceback * TimeStep , ... , endDate + T_traceback * TimeStep

        REMARK : if there are more than one start up and one shutdown over the period, the program will be considred as inconsistent.

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
        T_on = int(max(1, math.ceil(unit.minimum_time_on.total_minutes() / parameters.time_step)))
        T_off = int(max(1, math.ceil(unit.minimum_time_off.total_minutes() / parameters.time_step)))
        T_start = int(math.floor(unit.startup_duration.total_minutes() / parameters.time_step))
        T_stop = int(math.floor(unit.shutdown_duration.total_minutes() / parameters.time_step))

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
        states_sequence = Timeseries.from_index(extended_start_date, parameters.start_date, extended_end_date, 0)

        # Iterate trough the unit's maximum_power and based on the current value, determine whether the unit
        for t in extended_time_frame:
            if maximum_power.get_value(t) > 0:
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

                # See if the spell between the end of the start up and the begnning of the shutdown is greater than T_on
                if (end_of_shutdown - started_at_t).total_minutes() >= 0 and int(
                    math.floor((stopped_at_t - end_of_start_up).total_minutes() / parameters.time_step)
                ) < T_on:
                    inconsistent = True
                    return states_sequence, inconsistent
                # See if the spell between the end of the shutdown and the beginning of the shutdown is greater than T_off
                elif (end_of_shutdown - started_at_t).total_minutes() < 0 and int(
                    math.floor((started_at_t - end_of_shutdown).total_minutes() / parameters.time_step)
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
        states_sequence: Timeseries, orders_time: list[DateTime], parameters: DayAheadOrdersParameters, case=""
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
        online_at_t = []
        for t in orders_time:
            if states_sequence.get_value(t) != 0:
                online_at_t.append(t)

        # Based on these time steps, deduce the intervals.
        # The intervals bounds are retrieved by comparing the total minutes between to time steps :
        # if the total number of minutes is greater that TimeStep, then the time steps i and i+1 correspond to bounds of two distinct intervals
        intervals = []
        if online_at_t:
            intervals.append(online_at_t[0])
            if len(online_at_t) >= 2:
                for i in range(len(online_at_t) - 1):
                    if not (online_at_t[i + 1] - online_at_t[i]).total_minutes() == parameters.time_step:
                        intervals.append(online_at_t[i])
                        intervals.append(online_at_t[i + 1])
            intervals.append(online_at_t[-1])  # Add the element. This allows for potential singletons

        # Based on the interval boundaries, retrieve the intervals
        # If the unit is online over the whole orders_time time frame, then only one interval is generated
        # Otherwise all intervals are generated, using the fact that by construction, there is an even
        # number of time steps in the intervals list.
        list_of_online_timeframes = [Timeseries]
        if intervals:
            intervals.sort()
            for i in range(int(len(intervals) / 2)):
                window = states_sequence.slice_with_offset(intervals[2 * i], intervals[2 * i + 1])
                window.name = case
                list_of_online_timeframes.append(window)

            # Sanity check : remove potentials duplicates
            list_of_online_timeframes = list(dict.fromkeys(list_of_online_timeframes))

        return list_of_online_timeframes

    # ------ Main order formulation function, for base and intermediate units ------
    @staticmethod
    def formulate_unit_orders(
        online_timeframe: Timeseries,
        unit: Thermal,
        orders_time: list[DateTime],
        dataset: DayAheadOrdersInputDataset,
        parameters: DayAheadOrdersParameters,
        case="",
    ):
        """
        Formulate orders for one thermic power plant.

        Given a time series of states on which the unit is online (ON_., START and STOP), this function formulates orders according to the
        strategy presented in the documentation.

        Arguments
        `online_timeframe` : a time series over which the unit is online.
        `unit` : the unit for which the orders are formulated.
        `orders_time` : an index of dates over which orders will be formulated.
        `outputMarker` : the marker on which the orders are written
        `p` : a signed tuple of parameters
        `case` : (optional) a string that aims at identifying the price scenario if relevant

        Returns None
        """

        # Determine if the unit is offline or not. A sufficient condition is that the online_timeframe doesn't contain a 1
        # since by construction the unit is ON for at least one time step.
        # JL excludes an online sequence with an incomplete start-up ramp. For now, we will leave it as such.
        offline = True if 0 in online_timeframe.values() else False

        # If the unit is offline, no orders are formulated.
        if offline:
            if parameters.verbose:
                """TODO : add the sequence to make message more explicit"""
                cfg.logger.info(f"Unit {unit.name} is offline. No orders have been formulated for this unit")
            return None

        # If not offline, start the configuration of variables necessary for order formulation

        # Configuration of variables for orders' formulation
        ## Get the reserve procurements at the executionDate and collapse them into automated and manual reserves procurements
        automated_reserves_up_procured = unit.afrr_up_procured.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_date
        ) + unit.fcr_up_procured.get_forecast(parameters.execution_date, parameters.start_date, parameters.end_date)
        automated_reserves_down_procured = unit.afrr_down_procured.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_date
        ) + unit.fcr_down_procured.get_forecast(parameters.execution_date, parameters.start_date, parameters.end_date)
        manual_reserves_up_procured = unit.mfrr_up_procured.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_date
        ) + unit.rr_up_procured.get_forecast(parameters.execution_date, parameters.start_date, parameters.end_date)
        manual_reserves_down_procured = unit.mfrr_down_procured.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_date
        ) + unit.rr_down_procured.get_forecast(parameters.execution_date, parameters.start_date, parameters.end_date)

        ## Get the unit-specific parameters:
        T_start = int(math.floor(unit.startup_duration.total_minutes() / parameters.time_step))
        T_stop = int(math.floor(unit.shutdown_duration.total_minutes() / parameters.time_step))
        q_min = unit.minimum_power.max()

        ## See whether the unit will bid inflexible orders over the whole orders_time sequence:
        null_minimum_power = True
        for t in orders_time:
            if unit.minimum_power.get_value(t) != 0:
                null_minimum_power = False

        ## See whether there is a startup or not. Used to know if we need to amortise startup cost over the inflexible
        # orders or not.
        startup = True if 2 in online_timeframe.values() else False
        # if T_start > 0:
        #     startup = True if 2 in online_timeframe.Values else False
        # else:
        #     # Another way to check the startup, less efficient but more robust
        #     startup = False
        #     for t in list(online_timeframe.Index)[:-1]:
        #         t_next = t.AddMinutes(p.time_step)
        #         if online_timeframe.get_value(t_next) - online_timeframe.get_value(t) == 1:
        #             startup = True

        ## See whether the ramps are complete or not
        T_startSD_in_sim = False
        if 3 in online_timeframe.values():
            for t in list(online_timeframe.index)[:-1]:
                t_next = t + parameters.time_step
                if online_timeframe.get_value(t_next) - online_timeframe.get_value(t) == 2:
                    # passage from 1 to 3 in sequence, indicating the beginning of a shutdown
                    T_startSD_in_sim = True

        T_endSU_in_sim = False
        if startup:
            for t in list(online_timeframe.index)[:-1]:
                t_next = t.AddMinutes(parameters.time_step)
                if online_timeframe.get_value(t) - online_timeframe.get_value(t_next) == 1:
                    # passage from 2 to 1 in sequence, indicating the end of a startup
                    T_endSU_in_sim = True

        ## Extract K_start, K_stop.
        # K_start is the number of timesteps actually startup within the simulation timeframe (shorter than overall
        # timeframe used for computing states sequences).
        # K_start is the number of timesteps actually shutdown within the simulation timeframe (shorter than overall
        # timeframe used for computing states sequences).

        # Compute K_start and K_stop
        K_start, K_stop = 0, 0
        i, j = 0, 0
        for t in orders_time:
            if online_timeframe.get_value(t) == 2:
                i += 1
            elif online_timeframe.get_value(t) == 3:
                j += 1

        # Update the values
        K_start += i
        K_stop += j

        ## Definition of the time frames.
        ### Ramping timeframes: by construction, the associated start_time_frame and stop_time_frame
        # will be one time step longer than the usual start-up and shutdown periods.

        # Getting the starting date of the time frames.
        if K_start > 0 or K_stop > 0:
            for t in orders_time:
                if online_timeframe.get_value(t) == 2:
                    begin_of_startTimeFrame = t
                    break
            for t in orders_time:
                if online_timeframe.get_value(t) == 3:
                    begin_of_stopTimeFrame = t
                    break

        if K_start > 0:
            start_time_frame = generate_datetimes(
                begin_of_startTimeFrame, begin_of_startTimeFrame + K_start * parameters.time_step, parameters.time_step
            )
        if K_stop > 0:  # Shift by one time step because the time frame encompasses the last time step in the ON state
            # and remove one index because the last time step (null power) is formally excluded.
            stop_time_frame = generate_datetimes(
                begin_of_stopTimeFrame - parameters.time_step,
                begin_of_stopTimeFrame + (K_stop - 1) * parameters.time_step,
                parameters.time_step,
            )

        # In corner cases on the border of the time frame, remove excess time indexes.
        if K_start > 0:
            start_time_frame = [t for t in start_time_frame if t in orders_time]
        if K_stop > 0:
            stop_time_frame = [t for t in stop_time_frame if t in orders_time]

        ### FlexibleTimeFrame : all time indexes labelled with a 1 that are not in the start_time_frame or stop_time_frame
        # The potential overlapping is due to the fact that, by convention, the start and stop timeFrames are one time
        # step longer than the usual start-up and shutdown periods.
        # In case of startup: the last startup timestep, at Pmin, is the first one of the stable state sequence (state = 1),
        # to be removed from the flexible_time_frame.
        # In case of shutdown: the first shutdown timestep, at Pmin, is the last one of the orevious stable state sequence,
        # to be removed from the flexible_time_frame.
        flexible_time_frame = []
        for t in orders_time:
            if online_timeframe.get_value(t) == 1:
                flexible_time_frame.append(t)

        # Sanity check : the flexible_time_frame only contains timestamps within the orders_time time frame.
        flexible_time_frame = [t for t in flexible_time_frame if t in orders_time]

        # Remove potential overlapping time steps with the ramping timeframes.
        if K_start > 0:
            flexible_time_frame = [t for t in flexible_time_frame if t not in start_time_frame]
        if K_stop > 0:
            flexible_time_frame = [t for t in flexible_time_frame if t not in stop_time_frame]
            if K_start > 0:
                # Deal with the last corner case where the unit remains online for one time step. In this case, the overlapping time steps
                # between the start_time_frame and stop_time_frame is a singleton and by convention we remove this time step from the shutdown time frame.
                overlapping_time_steps = set(start_time_frame) & set(stop_time_frame)
                if len(overlapping_time_steps) == 1:
                    stop_time_frame = [t for t in stop_time_frame if t not in overlapping_time_steps]

        ## Inflexible timeframe
        inflexible_time_frame = online_timeframe.index

        # Formulate orders only if the unit is online

        # ------------------------------------------------------- #
        #                                                         #
        #                   Flexible layer                        #
        #                                                         #
        # ------------------------------------------------------- #
        # Loop over the flexible_time_frame to create the flexible orders first, formulated no matter what.
        for t, i in zip(flexible_time_frame, range(len(flexible_time_frame)), strict=False):
            # Part 1: flexible order
            # Compute the maximum amount to be offered.
            q_max = (
                unit.maximum_power.get_value(t)
                - unit.minimum_power.get_value(t)
                - manual_reserves_down_procured.get_value(t)
                - manual_reserves_up_procured.get_value(t)
                - automated_reserves_down_procured.get_value(t)
                - automated_reserves_up_procured.get_value(t)
            )

            # We only formulate the order if its maximal power is positive
            if q_max <= 0.0:
                if parameters.verbose:
                    cfg.logger.warning(
                        f"*** WARNING ***\n Negative or null amount of energy in the flexible order to be offered by unit {unit.name} at time {str(t)}. "
                        "The order will therefore not be created."
                    )

            else:
                # Flexible part of the order
                flexible_part = Order(
                    name=f"flexible_order_at_{Utilities.get_date_to_clean_string(t)}_for_unit_{unit.name}_with_price_{case}",
                    market_area=unit.portfolio.market_area,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=q_max,
                    qmin=0,
                    price=unit.variable_cost.get_value(t),
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=parameters.execution_date,
                    start_date=t,
                    end_date=t + parameters.time_step,
                )
                dataset.order.append(flexible_part)

            # Part 2: reserve requirement orders
            # Automated downard reserves requirements
            if automated_reserves_down_procured.get_value(t) > 0.0:
                # This order will be the child of the current inflexible order.
                # Initialize the order object.
                reserve_bid = Order(
                    name=f"automated_downward_reserve_order_at_{Utilities.get_date_to_clean_string(t)}_for_unit_{unit.name}_with_price_{case}",
                    market_area=unit.portfolio.market_area,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=automated_reserves_down_procured.get_value(t),
                    qmin=(1 - parameters.imposed_proportional_reserves_penalty)
                    * automated_reserves_down_procured.get_value(t),
                    price=unit.variable_cost.get_value(t) - parameters.automated_unprocured_reserves_penalty,
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=parameters.execution_date,
                    start_date=t,
                    end_date=t + parameters.time_step,
                )
                dataset.order.append(reserve_bid)

            # Manual downard reserves requirements
            if manual_reserves_down_procured.get_value(t) > 0.0:
                # This order will be the child of the current inflexible order.
                # Initialize the order object.
                reserve_bid = Order(
                    name=f"manual_downward_reserve_order_at_{Utilities.get_date_to_clean_string(t)}_for_unit_{unit.name}_with_price_{case}",
                    market_area=unit.portfolio.market_area,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=manual_reserves_down_procured.get_value(t),
                    qmin=(1 - parameters.imposed_proportional_reserves_penalty)
                    * manual_reserves_down_procured.get_value(t),
                    price=unit.variable_cost.get_value(t) - parameters.manual_unprocured_reserves_penalty,
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=parameters.execution_date,
                    start_date=t,
                    end_date=t + parameters.time_step,
                )
                dataset.order.append(reserve_bid)

            # Automated upward reserves requirements
            if automated_reserves_up_procured.get_value(t) > 0.0:
                # This order will be the child of the current flexible order.
                # Initialize the order object.
                reserve_bid = Order(
                    name=f"automated_upward_reserve_order_at_{Utilities.get_date_to_clean_string(t)}_for_unit_{unit.name}_with_price_{case}",
                    market_area=unit.portfolio.market_area,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=automated_reserves_up_procured.get_value(t),
                    qmin=(1 - parameters.imposed_proportional_reserves_penalty)
                    * automated_reserves_up_procured.get_value(t),
                    price=unit.variable_cost.get_value(t) + parameters.automated_unprocured_reserves_penalty,
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=parameters.execution_date,
                    start_date=t,
                    end_date=t + parameters.time_step,
                )
                dataset.order.append(reserve_bid)

            # Manual upward reserves requirements
            if manual_reserves_up_procured.get_value(t) > 0.0:
                # This order will be the child of the current flexible order.
                # Initialize the order object.
                reserve_bid = Order(
                    name=f"manual_upward_reserve_order_at_{Utilities.get_date_to_clean_string(t)}_for_unit_{unit.name}_with_price_{case}",
                    market_area=unit.portfolio.market_area,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=manual_reserves_up_procured.get_value(t),
                    qmin=(1 - parameters.imposed_proportional_reserves_penalty)
                    * manual_reserves_up_procured.get_value(t),
                    price=unit.variable_cost.get_value(t) + parameters.manual_unprocured_reserves_penalty,
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=parameters.execution_date,
                    start_date=t,
                    end_date=t + parameters.time_step,
                )
                dataset.order.append(reserve_bid)

        # ------------------------------------------------------- #
        #                                                         #
        #                   Inflexible layer                      #
        #                                                         #
        # ------------------------------------------------------- #
        # Add inflexible orders as a base if the minimum power of the unit is non-zero at least once during the day.
        # Add the corresponding parent/child couplings between the inflexible and flexible layers.
        if not null_minimum_power:
            # Compute the ramping gradients
            if T_start == 0:
                q_step_up = q_min
            else:
                q_step_up = q_min / T_start

            if T_stop == 0:
                q_step_down = q_min
            else:
                q_step_down = q_min / T_stop

            # Initialize the overall inflexible quantity offered, on which the startup cost will be spread afterwards
            Q = 0

            # Loop over the inflexible_time_frame to create the orders.
            inflexible_orders = []

            # Part 1: Startup orders
            # Does not create bids if there is not at least one stable state within the online sequence (prevents creating
            # unfinished startup ramps towards Pmin within the simulation timeframe for border case reasons.
            if K_start > 0:
                for t, i in zip(start_time_frame, range(K_start + 1), strict=False):
                    # Initialize the bid.

                    # Compute the parameters of the order
                    if T_endSU_in_sim:
                        q_sell = round((T_start - K_start + i) * q_step_up)
                    else:
                        q_sell = round(i * q_step_up)

                    bid_output = Order(
                        name=f"startup_ramp_order_at_{Utilities.get_date_to_clean_string(t)}_for_unit_{unit.name}_with_price_{case}",
                        market_area=unit.portfolio.market_area,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=q_sell,
                        qmin=q_sell,
                        price=unit.variable_cost.get_value(t),
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=parameters.execution_date,
                        start_date=t,
                        end_date=t + parameters.time_step,
                    )
                    dataset.order.append(bid_output)

                    inflexible_orders.append(bid_output)
                    Q += q_sell

            # Part 2: Shutdown orders
            # Does not create bids if there is not at least one stable state within the online sequence (prevents creating
            # shutdown ramps without the starting point at Pmin within the simulation timeframe for border case reasons.
            if K_stop > 0:
                for t, i in zip(stop_time_frame, range(K_stop + 1), strict=False):
                    # Initialize the bid.

                    # Compute the quantities to be sold.
                    if T_startSD_in_sim:
                        q_sell = round((T_stop - i) * q_step_down)
                    else:
                        q_sell = round(q_min - (T_stop - K_stop + i) * q_step_down)

                    bid_output = Order(
                        name=f"shutdown_ramp_order_at_{Utilities.get_date_to_clean_string(t)}_for_unit_{unit.name}_with_price_{case}",
                        market_area=unit.portfolio.market_area,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=q_sell,
                        qmin=q_sell,
                        price=round(unit.variable_cost.get_value(t), 2),
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=parameters.execution_date,
                        start_date=t,
                        end_date=t + parameters.time_step,
                    )
                    dataset.order.append(bid_output)

                    inflexible_orders.append(bid_output)
                    Q += q_sell

            # Part 3: inflexible orders at Pmin
            for t, i in zip(flexible_time_frame, range(len(flexible_time_frame)), strict=False):
                # Initialize the inflexible order object.
                bid_output = Order(
                    name=f"order_at_{Utilities.get_date_to_clean_string(t)}_for_unit_{unit.name}_under_price_{case}",
                    market_area=unit.portfolio.market_area,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=unit.minimum_power.get_value(t),
                    qmin=unit.minimum_power.get_value(t),
                    price=round(unit.variable_cost.get_value(t), 2),
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=parameters.execution_date,
                    start_date=t,
                    end_date=t + parameters.time_step,
                )
                dataset.order.append(bid_output)

                inflexible_orders.append(bid_output)
                Q += unit.minimum_power.get_value(t)

                # Check the existence of flexible bids to be linked by a parent-child coupling
                flexible_types = [
                    "flexible_order",
                    "manual_upward_reserve_order",
                    "automated_upward_reserve_order",
                    "manual_downward_reserve_order",
                    "automated_downward_reserve_order",
                ]
                for flex_type in flexible_types:
                    config_bid_name = (
                        f"_at_{Utilities.get_date_to_clean_string(t)}_for_unit_{unit.name}_with_price_{case}"
                    )
                    flexible_bid_name = flex_type + config_bid_name
                    flexible_bid = next((bid for bid in dataset.order if bid.name == flexible_bid_name), None)
                    if flexible_bid is not None:
                        ThermicBidding.create_parent_child_link(dataset, bid_output, flexible_bid, case, unit, t)

            # Part 4: configure the identical_ratio link between all inflexible orders
            date = inflexible_time_frame[0]
            coupling = OrderCoupling(
                name=f"IDENTICAL_RATIO_inflexible_orders_for_unit_{unit.name}_starting_at_{Utilities.get_date_to_clean_string(date)}_with_price_{case}",
                coupling_type=CouplingType.IDENTICAL_RATIO,
            )
            for order in inflexible_orders:
                coupling.orders.append(order)
            dataset.order_coupling.append(coupling)

            # Part 5 : if startup, amortise startup cost on all inflexible layer
            amortized_cost = round(unit.startup_cost.get_value(t) / Q, 2)
            for order in inflexible_orders:
                # Add the spreading of start up cost only if the startup is complete within the sequence
                if startup and T_endSU_in_sim:
                    order.price += amortized_cost
                else:
                    order.price -= amortized_cost

        return None

    @staticmethod
    def create_parent_child_link(
        dataset: DayAheadOrdersInputDataset, parent_bid: Order, child_bid: Order, case: str, unit: Thermal, t: DateTime
    ):
        # Add parent-children link between the flexible and inflexible parts
        link_flexible_inflexible = OrderCoupling(
            name=f"PARENT_CHILDREN_inflexible_flexible_orders_at_{Utilities.get_date_to_clean_string(t)}_for_unit_{unit.name}_with_price_{case}",
            coupling_type=CouplingType.PARENT_CHILDREN,
        )
        # add the two orders
        link_flexible_inflexible.orders.append(parent_bid)
        link_flexible_inflexible.orders.append(child_bid)
