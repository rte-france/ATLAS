"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math
import os
from datetime import datetime

import atlas.config as cfg
from atlas.modules.day_ahead_orders.tools.Utilities import Utilities
from atlas.math.timeseries import Timeseries
from atlas import generate_datetimes, OptimisationModel
from atlas.models.equipment.thermal import Thermal
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters


class ThermicOptimization:
    @staticmethod
    def solve_optimization_programs(equipments_list: Thermal, parameters: DayAheadOrdersParameters) -> dict:
        """
        Solves the optimization programs for a list of equipment given the three price curves.

        Arguments:
        equiment_list : a list of thermal equipments
        parameters : a signedTuple of parameters

        Returns:
        results : a two stage dictionary containing for each equipment the optimal quantities given a price curve.
        lp_files : a two stage dictionary containing for each equipment and each price curve the associated lp file
                    of the optimization program.
        """

        # create a dictionary that will store the program's outcomes.
        results = {}

        for unit, i in zip(equipments_list, range(len(equipments_list)), strict=False):
            # Initialize a key with the unit's name.
            results[unit.name] = {}

            # Retrieve the price forecasts types, extract the corresponding time series and store it in a list
            price_types = parameters.price_forecasts_types
            prices = []

            for price_type in price_types:
                if price_type == "Low":
                    prices_low = unit.portfolio.market_area.price_forecast_low.get_forecast(
                        parameters.execution_date, parameters.start_date, parameters.end_optimization_date
                    )
                    prices.append(prices_low)

                elif price_type == "Medium":
                    prices_medium = unit.portfolio.market_area.price_forecast_medium.get_forecast(
                        parameters.execution_date, parameters.start_date, parameters.end_optimization_date
                    )
                    prices.append(prices_medium)

                elif price_type == "High":
                    prices_high = unit.portfolio.market_area.price_forecast_high.get_forecast(
                        parameters.execution_date, parameters.start_date, parameters.end_optimization_date
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
                res = ThermicOptimization.solve_thermic_optimization_program(unit, price, value, parameters)
                results[unit.name][value] = res

                # Store state sequences in the output marker
                local_time_index = res["OFF"].index()
                # TODO
                new_sequence_ts = API.TimeSeries.NewTimeSeries(
                    "State_sequence_of_{}_{}_price".format(unit.Name, value),
                    API.TimeSeries.Constant,
                    "Integer",
                    local_time_index,
                    0,
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

                unit.state_sequence.add(
                    f"{Utilities.get_date_to_clean_string(parameters.execution_date)}-{value.upper()}_DAO",
                    new_sequence_ts,
                )

        return results

    @staticmethod
    def solve_thermic_optimization_program(
        thermal_unit: Thermal, prices, price_type, parameters: DayAheadOrdersParameters
    ):
        """
        This function solves the optimization program associated to the thermic units. It only
        performs the optimization for one unit, passed as an argument.
        Optimization is done over the extended optimization period, ie between StartDate - epsilon
        and endOptimizationDate + epsilon where epsilon is an additional time corresponding to
        the maximum between the minimum duration time and the startup duration.
        Optimization is done with respect to a price sequence given as an argument.

        Arguments:
        - `thermal_unit`: an Thermal instance.
        - `prices`: a price timeseries based on which optimization will be conducted.
        - `parameters` a DayAheadOrdersParameters.

        Returns:
        - `results`: a dictionnary containing the optimal values of the decision variables,
        namely :
            . q*, the optimal power output
            . ON_.*, OFF*, START* and STOP* (when relevant), the optimal values of the state variables
        All these results are returned in the form of a TimeSeries object ranging over the optimization period
        (i.e. [startDate, endOptimizationDate]).
        """

        if parameters.solver.upper() != "XPRESS":
            # If another solver is being used, consider setting the NoOverlap parameter to False as it previsously raised errors otherwise with GLPK
            raise ValueError(
                "Please use XPRESS, as other solvers either are deprecated or provide non-optimal solutions"
            )

        model = OptimisationModel(
            solver_name=parameters.solver.upper(),
            name="Optimization program for thermal unit {}".format(thermal_unit.name),
        )

        # Quick sanity check on the class of the equipment supplied as input.
        if not type(thermal_unit).__name__ == "Thermal":
            cfg.logger.error("*** WARNING ***\n Equipement {} is not of type thermic.".format(thermal_unit.name))
            raise ValueError("Wrong equipment type for the thermic optimization program.")

        # ---------------------------------------------------#
        #                                                   #
        # STEP 0 : Retrieve the parameters of the program   #
        #          and set up the time frame                #
        #                                                   #
        # ---------------------------------------------------#

        # Sanity check on the startDate and the endDate. A warning message is sent to the user if the startDate is later
        # than the endDate.
        if parameters.start_date > parameters.end_optimization_date:
            cfg.logger.error(
                "*** WARNING ***\n The endOptimizationDate is earlier than or identical to the startDate. \n"
                "The time frame cannot be defined. Please check the values of StartDate, EndDate and AdditionalHours"
            )
            raise ValueError("Improper dates")

            # Get the parameters of the unit
        fcr_up_procured = thermal_unit.fcr_up_procured.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_optimization_date
        )
        fcr_down_procured = thermal_unit.fcr_down_procured.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_optimization_date
        )
        afrr_up_procured = thermal_unit.afrr_up_procured.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_optimization_date
        )
        afrr_down_procured = thermal_unit.afrr_down_procured.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_optimization_date
        )
        mfrr_up_procured = thermal_unit.mfrr_up_procured.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_optimization_date
        )
        mfrr_down_procured = thermal_unit.mfrr_down_procured.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_optimization_date
        )
        rr_up_procured = thermal_unit.rr_up_procured.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_optimization_date
        )
        rr_down_procured = thermal_unit.rr_down_procured.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_optimization_date
        )

        # Check that the minimum_stable_power_duration is smaller than the minimumTimeOn
        # if not thermal_unit.minimum_stable_power_duration <= thermal_unit.minimum_time_on:
        #    # Warn the user
        #    warning_message =  """
        #        *** WARNING *** \n
        #        the minimum_stable_power_duration of equipment {} is greater than its minimum_time_on.\n
        #        minimum_stable_power_duration has been modified and is now considered equal to minimum_time_on.
        #        """.format(thermal_unit.name)
        #    if p.verbose:
        #        API.IO.Trace.Log(warning_message)

        #    # Change the value of minimum_stable_power_duration
        #    # Take the maximum between 1 and minimumTimeOn because T_on > 0
        #    minimum_stable_power_duration = max(1, thermal_unit.minimum_time_on) # Enforces equations (1) of the documentation
        # else:
        #    minimum_stable_power_duration = thermal_unit.minimum_stable_power_duration
        minimum_stable_power_duration = thermal_unit.minimum_stable_power_duration

        # Conversion of the equipment-specific parameters in terms of time step.
        # All T_.'s are integers (by definition).
        if thermal_unit.minimum_time_on > 0:
            T_on = int(max(1, math.ceil(thermal_unit.minimum_time_on.total_minutes() / parameters.time_step))) + 1
        else:
            T_on = 0

        if thermal_unit.minimum_time_off > 0:
            T_off = int(max(1, math.ceil(thermal_unit.minimum_time_off.total_minutes() / parameters.time_step))) + 1
        else:
            T_off = 0
        T_start = int(math.floor(thermal_unit.startup_duration.total_minutes() / parameters.time_step))
        T_stop = int(math.floor(thermal_unit.shutdown_duration.total_minutes() / parameters.time_step))

        if minimum_stable_power_duration.total_minutes() >= parameters.time_step:
            T_stable = int(math.ceil(minimum_stable_power_duration.total_minutes() / parameters.time_step)) + 1
        else:
            T_stable = 0

        # Rescale T_stable so that it is either equal to 0 or >= 2:
        T_stable = T_stable if T_stable >= 2 else 0

        # Set-up the time frames
        # Definition of the time_frame time frame : the time frame on which
        # the optimization program will be solved.
        # Remark: we define the time series until endDate - TimeStep because
        # we want all time steps to lie in the [startDate, endOptimizationDate] range.
        end_date = parameters.end_optimization_date - parameters.time_step
        time_frame = generate_datetimes(parameters.start_date, end_date, parameters.time_step)

        # Define T_traceback, the number of timesteps we need to go before startDate to define the initial conditions.
        # We add +1 in order to avoid out-of-bounds errors when defining the ON_FLAT state.
        T_traceback = int(max(T_on + T_start, T_off + T_stop)) + 1

        # Define manually the previous_time_frame, which contains all time steps from startDate to (startDate - T_traceback * TimeStep)
        previous_time_frame = []
        for k in range(1, T_traceback + 1):
            previous_time_frame.append(parameters.start_date - k * parameters.time_step)

            # Define the extendedTimeFrame, ranging from the last element of the previous_time_frame to endOptimizationDate.
        # We also start from 1 in order to exclude startDate from the previous_time_frame.
        extended_start_date = previous_time_frame[-1]  # Last date in the previous_time_frame

        # Set-up the power bounds : copy maximum- and minimumPower
        # because q_lower and q_upper may be modified afterwards.
        q_lower = Timeseries.from_timeseries(thermal_unit.minimum_power)
        q_upper = Timeseries.from_timeseries(thermal_unit.maximum_power)

        # Set-up the reserve requirements
        # Compute the maximum_automated
        maximum_automated = thermal_unit.maximum_afrr + thermal_unit.maximum_fcr

        # Add the manual reserves (referred to as "reserves" in the following)
        # Reserves
        reserves_up_procured = mfrr_up_procured + rr_up_procured
        reserves_down_procured = mfrr_down_procured + rr_down_procured
        # Compute the feasibleAutomatedReserves. This is to accomodate for the fact that the maximumAFRR and maximumFCR capacities
        # may be different.If the unit has a procurement greater than its capacity, the remaning part will be unsupplied and counted
        # in a penalty added in the objective function.

        # Create the time series of feasible automated reserves procurements
        feasible_automated_reserves_up_procured = Timeseries.from_index(
            parameters.start_date, parameters.timestep, end_date, default_value=0
        )
        feasible_automated_reserves_down_procured = Timeseries.from_index(
            parameters.start_date, parameters.timestep, end_date, default_value=0
        )

        # Populate the time series and retrieve the infeasible automated reserve procurements.
        automated_unsupplied_reserves = 0
        for t in time_frame:
            # retrieve the feasible part in the feasible time series
            feasible_automated_reserves_up_procured[t] = min(
                afrr_up_procured.get_value(t), thermal_unit.maximum_afrr
            ) + min(fcr_up_procured.get_value(t), thermal_unit.maximum_fcr)
            feasible_automated_reserves_down_procured[t] = min(
                afrr_down_procured.get_value(t), thermal_unit.maximum_afrr
            ) + min(fcr_down_procured.get_value(t), thermal_unit.maximum_fcr)

            # retrieve and save the infeasible part
            automated_unsupplied_reserves += (
                max(afrr_up_procured.get_value(t) - thermal_unit.maximum_afrr, 0)
                + max(fcr_up_procured.get_value(t) - thermal_unit.maximum_fcr, 0)
                + max(afrr_down_procured.get_value(t) - thermal_unit.maximum_afrr, 0)
                + max(fcr_down_procured.get_value(t) - thermal_unit.maximum_fcr, 0)
            )

        if parameters.verbose:
            cfg.logger.info("automated unsupplied reserves : {}".format(automated_unsupplied_reserves))

        # Set-up the power gradients
        delta_q = thermal_unit.maximum_gradient * parameters.time_step
        delta_q_unconstrained = thermal_unit.maximum_power.max()

        # -------------------------------------------------------------------#
        #                                                                   #
        # STEP 1 : Definition of the state, auxiliary and control variables #
        #          over the time_frame.                                      #
        #                                                                   #
        # -------------------------------------------------------------------#

        # 1.1. Control variables :
        #    - the power output of the unit
        #    - the reserves of the unit and the mirror variables
        #    - contracted difference which corresponds to max(procured - provided, 0).
        # Initialize the dictionnary
        q = {}
        # Define the main optimization variable. Bounds : O and q_upper
        for t in time_frame:
            q[t] = model.add_continuous_variable(
                "power_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                0,
                q_upper.get_value(t),
            )

        # Define the reserves variables
        # reserves_up and reserves_down are defined no matter the value of T_stable. Only the type of reserves it encompasses changes.
        reserves_up = {}
        reserves_down = {}
        unprovided_reserves_up = {}
        unprovided_reserves_down = {}
        relaxed_reserves = {}
        for t in time_frame:
            reserves_up[t] = model.add_continuous_variable(
                "reservesUp_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                0,
                q_upper.get_value(t),
            )

            reserves_down[t] = model.add_continuous_variable(
                "reservesDown_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                0,
                q_upper.get_value(t),
            )

            unprovided_reserves_up[t] = model.add_continuous_variable(
                "unprovidedReservesUp_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                0,
                q_upper.get_value(t),
            )

            unprovided_reserves_down[t] = model.add_continuous_variable(
                "unprovidedReservesDown_equip_{}_at_{}".format(
                    thermal_unit.name, Utilities.get_date_to_clean_string(t)
                ),
                0,
                q_upper.get_value(t),
            )

            relaxed_reserves[t] = model.add_continuous_variable(
                "relaxedReserves_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                0,
                q_lower.get_value(t),
            )

            # create the automatedReserves control variables.
        automated_reserves_up = {}
        automated_reserves_down = {}
        for t in time_frame:
            automated_reserves_up[t] = model.add_continuous_variable(
                "automatedReservesUp_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                0,
                maximum_automated,
            )

            automated_reserves_down[t] = model.add_continuous_variable(
                "automatedReservesDown_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                0,
                maximum_automated,
            )

        # Create the contractedDifference variables. These variables are implemented as control variables will be included in the
        # objective function and constrained by constraint (40).
        contracted_difference_up = {}
        contracted_difference_down = {}
        for t in time_frame:
            contracted_difference_up[t] = model.add_continuous_variable(
                "contractedDifferenceUp_equip_{}_at_{}".format(
                    thermal_unit.name, Utilities.get_date_to_clean_string(t)
                ),
                0,
                q_upper.get_value(t),
            )
            contracted_difference_down[t] = model.add_continuous_variable(
                "contractedDifferenceDown_equip_{}_at_{}".format(
                    thermal_unit.name, Utilities.get_date_to_clean_string(t)
                ),
                0,
                q_upper.get_value(t),
            )

        # Automated contracted difference variables. These variables will be constrained by equation (39).
        automated_contracted_difference_up = {}
        automated_contracted_difference_down = {}
        for t in time_frame:
            automated_contracted_difference_up[t] = model.add_continuous_variable(
                "automatedContractedDifferenceUp_equip_{}_at_{}".format(
                    thermal_unit.name, Utilities.get_date_to_clean_string(t)
                ),
                0,
                q_upper.get_value(t),
            )
            automated_contracted_difference_down[t] = model.add_continuous_variable(
                "automatedContractedDifferenceDown_equip_{}_at_{}".format(
                    thermal_unit.name, Utilities.get_date_to_clean_string(t)
                ),
                0,
                q_upper.get_value(t),
            )

        # 1.2. State variables (always in upper case)

        # 1.2.1. Initialization of the state variables that are always defined :
        # OFF, ON_UP, ON_FLAT and ON_DOWN
        # Initialize the dictionnaries
        OFF = {}
        ON_DOWN = {}
        ON_UP = {}

        # Create the state variables for each time step over the extended time frame.
        for t in time_frame:
            OFF[t] = model.add_boolean_variable(
                "OFF_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t))
            )
            ON_UP[t] = model.add_boolean_variable(
                "ON_UP_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t))
            )
            ON_DOWN[t] = model.add_boolean_variable(
                "ON_DOWN_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t))
            )

        # 1.2.2. 'Conditional' state variables : defined only if a certain criteria on T is met.
        if T_start >= 1:
            # Define the start_time_steps range, i.e. the interval {1,...,T_start - 1}
            start_time_steps = range(1, T_start - 1)

            # Define the START state variable.
            START = {}
            for t in time_frame:
                START[t] = model.add_boolean_variable(
                    "START_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t))
                )

        if T_stop >= 1:
            # Define the stop_time_steps range.
            stop_time_steps = range(1, T_stop - 1)

            # Define the STOP state variable
            STOP = {}
            for t in time_frame:
                STOP[t] = model.add_boolean_variable(
                    "STOP_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t))
                )

        if T_stable >= 1:
            start_date_minus_one = parameters.start_date - parameters.time_step
            ON_FLAT = {}
            for t in time_frame:
                ON_FLAT[t] = model.add_boolean_variable(
                    "ON_FLAT_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t))
                )

            # For the time step startDate - 1, create optimization avariables for ON_FLAT, ON_UP and ON_DOWN
            ON_FLAT[start_date_minus_one] = model.add_boolean_variable(
                "ON_FLAT_equip_{}_at_{}".format(
                    thermal_unit.name, Utilities.get_date_to_clean_string(start_date_minus_one)
                )
            )

            ON_DOWN[start_date_minus_one] = model.add_boolean_variable(
                "ON_DOWN_equip_{}_at_{}".format(
                    thermal_unit.name, Utilities.get_date_to_clean_string(start_date_minus_one)
                )
            )

            ON_UP[start_date_minus_one] = model.add_boolean_variable(
                "ON_UP_equip_{}_at_{}".format(
                    thermal_unit.name, Utilities.get_date_to_clean_string(start_date_minus_one)
                )
            )

        # 1.3. Auxiliary variables
        # Remark. Auxiliary variables are formally binary variables but due to their
        # defining constraints (see below), they can be defined as continuous values comprised in [0,1].
        # Constraints will ensure that the value they take is always 0 or 1.
        # Convention : auxiliary variables are written in lower case

        # 1.3.1. Create the auxiliary variables that will always be defined
        turned_on = {}  # Corresponding to the variable defined in sec. 6.1.1
        turned_off = {}  # Corresponding to the variable defined in sec. 6.1.2
        for t in time_frame:
            turned_on[t] = model.add_continuous_variable(
                "turned_on_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)), 0, 1
            )

            turned_off[t] = model.add_continuous_variable(
                "turned_off_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)), 0, 1
            )

        # 1.3.2. Create the condtionnal auxiliary variables if necessary.

        # Variable indicating that the unit is stable at t (sec. 6.1.3)
        # and variables to constrain the gradient U[t], D[t] and tilde_U[t], tilde_D[t] (defined in sec 6.2.4.)
        if T_stable >= 1:
            # Define the time_frame_union_minus_one which includes the start_date_minus_one time step.
            time_frame_union_minus_one = generate_datetimes(
                parameters.start_date - parameters.time_step,
                parameters.end_optimization_date - parameters.time_step,
                parameters.time_step,
            )

            # Define dummy bounds for the gradient auxiliaries
            Q_max = delta_q_unconstrained
            Q_min = -Q_max

            stable = {}  # This auxiliary variable indicates when the unit enters the FLAT state
            entered_up = {}  # This variable replaces ON_UP in the definition of the gradient and will bound the gradient for only one time step
            entered_down = {}  # Same as single_on_up but for on down

            U = {}  # This variable will be implemented in the gradient and bound the upward gradient
            tilde_U = {}
            D = {}  # This variable will be implemented in the gradient and bound the downward gradient
            tilde_D = {}

            for t in time_frame_union_minus_one:
                # Define the auxiliary variables of this state.
                stable[t] = model.add_continuous_variable(
                    "stable_at_{}_equip_{}".format(Utilities.get_date_to_clean_string(t), thermal_unit.name), 0, 1
                )
                entered_up[t] = model.add_continuous_variable(
                    "entered_up_at_{}_equip_{}".format(Utilities.get_date_to_clean_string(t), thermal_unit.name), 0, 1
                )
                entered_down[t] = model.add_continuous_variable(
                    "entered_down_at_{}_equip_{}".format(Utilities.get_date_to_clean_string(t), thermal_unit.name), 0, 1
                )

            for t in time_frame:
                # Initialize the gradient auxiliaries.
                U[t] = model.add_continuous_variable(
                    "UP_grad_at_{}_equip_{}".format(Utilities.get_date_to_clean_string(t), thermal_unit.name),
                    Q_min,
                    Q_max,
                )
                D[t] = model.add_continuous_variable(
                    "DOWN_grad_at_{}_equip_{}".format(Utilities.get_date_to_clean_string(t), thermal_unit.name),
                    Q_min,
                    Q_max,
                )
                tilde_U[t] = model.add_continuous_variable(
                    "aux_up_grad_at_{}_equip_{}".format(Utilities.get_date_to_clean_string(t), thermal_unit.name),
                    Q_min,
                    Q_max,
                )
                tilde_D[t] = model.add_continuous_variable(
                    "aux_down_grad_at_{}_equip_{}".format(Utilities.get_date_to_clean_string(t), thermal_unit.name),
                    Q_min,
                    Q_max,
                )

        # -----------------------------#
        #                             #
        # STEP 2 : Objective function #
        #                             #
        # -----------------------------#

        # Set-up the objective function given by eq. (2) in the documentation.
        # If T_stable = 0, we don't need to include automatedContractedReservesUp and automatedContractedReservesDown to the objective function.
        # otherwise we need to include them.
        model.add_objective(
            objective_expr=(
                sum(
                    q[t]
                    * (parameters.time_step.total_hours())
                    * (prices.get_value(t) - thermal_unit.variable_cost.get_value(t))
                    - turned_on[t] * thermal_unit.startup_cost.get_value(t)
                    - parameters.manual_unprocured_reserves_penalty
                    * (parameters.time_step.total_hours())
                    * (contracted_difference_up[t] + contracted_difference_down[t])
                    - parameters.automated_unprocured_reserves_penalty
                    * (parameters.time_step.total_hours())
                    * (automated_contracted_difference_up[t] + automated_contracted_difference_down[t])
                    for t in time_frame
                )
                - parameters.automated_unprocured_reserves_penalty
                * (parameters.time_step.total_hours())
                * automated_unsupplied_reserves
            ),
            direction="maximize",
        )

        # ---------------------------------------------#
        #                                             #
        # STEP 3 : Constraints and initial conditions #
        #                                             #
        # ---------------------------------------------#

        # Constraints and initial conditions are defined based on state and auxiliary variables.
        # Since these variables are not necessarily defined, in the following we go through all
        # 8 possible combinations of state and auxiliary variables and write the corresponding
        # initial conditions and set of constraints all at once.
        #
        # Initial conditions are defined on the previous_time_frame, constraints on the state and
        # control variables are defined on the time_frame.

        # --------------------------------------------------------------------------------------------- #
        ################# ------ Constraints and initial conditions combinations ------ #################
        # --------------------------------------------------------------------------------------------- #

        # ---------------------------------------------------------#
        #                                                         #
        ##### Combination 1 : T_stop = T_stable = T_start = 0 #####
        #                                                         #
        # ---------------------------------------------------------#

        if T_stop == 0 and T_start == 0 and T_stable == 0:
            # In this case, there are three state variables and two auxiliary variables.
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # A. INITIAL CONDITIONS

            # Retrieve the values of the Power attribute over previous_time_frame
            last_power = thermal_unit.power.get_forecast(
                parameters.execution_date, extended_start_date, parameters.start_date - parameters.time_step
            )  # Extract the time series corresponding to the previous period
            last_date = last_power.last_date  # get the last date with a recorded value

            # See if the program needs to be initialized as DayZero or not
            if len(last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif last_date != parameters.start_date - parameters.time_step:
                # last_date doesn't match startDate - TimeStep (i.e. t_{-1},
                # so we will initialize as DayZero and send a warning message
                if parameters.verbose:
                    cfg.logger.warning(
                        "***WARNING***\n The last_date found in Power of equipement {} "
                        "does not match the startDate of the current program. \n "
                        "The program will be initialized as DayZero.".format(thermal_unit.name)
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if parameters.verbose:
                    cfg.logger.info(
                        "Initial conditions of unit {} have been set as in equation (47).".format(thermal_unit.name)
                    )

                for t in previous_time_frame:
                    # Initial conditions on the power output
                    q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    OFF[t] = 1
                    ON_UP[t] = 0
                    ON_DOWN[t] = 0
                    # Initial conditions on the auxiliary variables
                    turned_on[t] = 0
                    turned_off[t] = 0
            else:
                # Initial condition on the power output
                for t in previous_time_frame:
                    q[t] = last_power.get_value(t)

                # Initial conditions on the state variables
                # Only need to set one value, the mutual exclusion constraint being defined over the
                # whole extended time frame.
                for t in previous_time_frame:
                    if last_power.get_value(t) > 0:
                        OFF[t] = 0
                        ON_DOWN[t] = 1
                        ON_UP[t] = 1
                    else:
                        OFF[t] = 1
                        ON_UP[t] = 0
                        ON_DOWN[t] = 0

                # Initial conditions on the auxiliary variables
                for t in previous_time_frame:
                    # Initialize all the values to 0
                    turned_on[t] = 0
                    turned_off[t] = 0
                    if not t == extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - parameters.time_step
                        # See if the unit has been turned off
                        if OFF[t] - OFF[t_prev] == 1:
                            turned_off[t] = 1
                        # Or turned on
                        elif OFF[t] - OFF[t_prev] == -1:
                            turned_on[t] = 1
                        else:
                            turned_on[t] = 0
                            turned_off[t] = 0

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them : turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Enforces equation (3)
            for t in time_frame:
                model.add_constraint(turned_on[t] <= 1 - OFF[t])
                model.add_constraint(turned_on[t] <= OFF[t - parameters.time_step])
                model.add_constraint(turned_on[t] >= OFF[t - parameters.time_step] - OFF[t])

                # Constraints on turned_off
            # STOP is not defined in this case, so we enforce equation (4)
            for t in time_frame:
                model.add_constraint(turned_off[t] <= 1 - OFF[t - parameters.time_step])
                model.add_constraint(turned_off[t] <= OFF[t])
                model.add_constraint(turned_off[t] >= OFF[t] - OFF[t - parameters.time_step])

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in time_frame:
                # Defined over the whole time frame
                # Enforces eq. (9)
                model.add_constraint(OFF[t] + ON_UP[t] + ON_DOWN[t] == 1)

            # Transitions:
            # None. All transitions are allowed

            # Mininum time on and minimum time off constraints:
            # if T_on >= 2 or T_off >= 2, lock the unit in this state.
            if T_on >= 2:
                for t in time_frame:
                    time_steps = range(1, T_on)  # Corresponds to the set {1, ..., T_on -1}
                    for s in (
                        time_steps
                    ):  # Add the constraints given by eq. (31), here T_start = 0 so t - s - T_start = t - s
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            turned_on[t_minus_s] <= ON_UP[t] + ON_DOWN[t],
                            "minimum_time_ON_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )

            if T_off >= 2:
                for t in time_frame:
                    time_steps = range(1, T_off)  # Corresponds to the set {1, ..., T_off -1}
                    for (
                        s
                    ) in time_steps:  # Add the constraints given by eq. (32), here T_stop = 0 so t - s - T_stop = t - s
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            turned_off[t_minus_s] <= OFF[t],
                            "minimum_time_OFF_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))
            for t in time_frame:
                # contractedDifference
                model.add_constraint(contracted_difference_up[t] >= reserves_up_procured.get_value(t) - reserves_up[t])
                model.add_constraint(
                    contracted_difference_down[t] >= reserves_down_procured.get_value(t) - reserves_down[t]
                )
                # automatedContractedDifference
                model.add_constraint(
                    automated_contracted_difference_up[t]
                    >= feasible_automated_reserves_up_procured[t] - automated_reserves_up[t]
                )
                model.add_constraint(
                    automated_contracted_difference_down[t]
                    >= feasible_automated_reserves_down_procured[t] - automated_reserves_down[t]
                )

            # Upward and downward "fill up" constraints.
            for t in time_frame:
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    <= q_upper.get_value(t) + parameters.epsilon
                )  # Upward constraint - eq. (41)
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    >= q_upper.get_value(t) - parameters.epsilon
                )  # Upward constraint - eq. (41)

                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    <= q_lower.get_value(t) + parameters.epsilon
                )  # Downward constraint - eq. (42)
                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    >= q_lower.get_value(t) - parameters.epsilon
                )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            for t in time_frame:
                model.add_constraint(relaxed_reserves[t] <= q_lower.get_value(t) * (1 - ON_UP[t] - ON_DOWN[t]))

            # impossible commitment and stable reserves constraints (eq. (44))
            for t in time_frame:
                model.add_constraint(automated_reserves_up[t] <= maximum_automated * (1 - OFF[t]))
                model.add_constraint(automated_reserves_down[t] <= maximum_automated * (1 - OFF[t]))
                model.add_constraint(reserves_up[t] <= q_upper.get_value(t) * (1 - OFF[t]))
                model.add_constraint(reserves_down[t] <= q_upper.get_value(t) * (1 - OFF[t]))

                # Power output
            for t in time_frame:
                model.add_constraint(
                    q[t] >= q_lower.get_value(t) * (ON_UP[t] + ON_DOWN[t]),
                    "lower_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Lower bound (eq. 33)

                model.add_constraint(
                    q[t] <= q_upper.get_value(t) * (ON_UP[t] + ON_DOWN[t]),
                    "upper_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Upper bound (eq. 34)

            # Power gradients
            # Definition of the gradients_time_frame : starts at startDate - TimeStep and goes until T-1
            # Gradients are defined on a "shifted" time frame.
            gradients_time_frame = generate_datetimes(
                parameters.start_date - parameters.time_step,
                parameters.end_optimization_date - 2 * parameters.time_step,
                parameters.time_step,
            )

            if delta_q > 0:  # Case where the gradient is finite.
                for t in gradients_time_frame:  # The gradients are defined only up to T-1.
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. 35):
                    model.add_constraint(
                        q[t_next] - q[t] <= delta_q * ON_UP[t] + delta_q_unconstrained * turned_on[t_next],
                        "upward_gradient_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                    )  # Upward gradient

                    # Downward constrained gradient (eq. 37) :
                    model.add_constraint(
                        q[t_next] - q[t] >= -delta_q * ON_DOWN[t] - delta_q_unconstrained * turned_off[t_next],
                        "downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient

            elif delta_q == 0:  # Case where the gradient is 'infinite'
                for t in gradients_time_frame:
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward unconstrained gradient (eq. 36)
                    model.add_constraint(
                        q[t_next] - q[t] <= delta_q_unconstrained * ON_UP[t] + delta_q_unconstrained * turned_on[t_next]
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. 38)
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= -delta_q_unconstrained * ON_DOWN[t] - delta_q_unconstrained * turned_off[t_next]
                    )  # Downward gradient
            else:  # Raise an error since no gradients have been detected.
                cfg.logger.warning(
                    "*** WARNING ***\n No gradients have been defined for equipment {}. \n "
                    "Please check the value of `maximum_gradient`.".format(thermal_unit.name)
                )
                raise ValueError("Missing gradients for thermic units.")

                # Energy limits
            if thermal_unit.has_daily_energy_constraint:
                days_in_time_frame = []

                for local_time in time_frame:
                    if datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0) not in days_in_time_frame:
                        days_in_time_frame.append(datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0))

                for date in days_in_time_frame:
                    upper_bound = thermal_unit.maximum_daily_energy.get_value(date)

                    matching_steps = []
                    for local_time in time_frame:
                        if (
                            (local_time.year == date.year)
                            and (local_time.month == date.month)
                            and (local_time.day == date.day)
                        ):
                            matching_steps.append(local_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        model.add_constraint(
                            sum(q[t] for t in matching_steps)
                            <= upper_bound * parameters.time_step / 1440.0 * len(matching_steps),
                            "energy_limit_of_{}_at_{}".format(
                                thermal_unit.name, Utilities.get_date_to_clean_string(date)
                            ),
                        )
                        # TimeStep / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                             #
        ##### Combination 2 : T_stop >= 1, T_stable = T_start = 0 #####
        #                                                             #
        # -------------------------------------------------------------#

        if T_stop >= 1 and T_start == 0 and T_stable == 0:
            # In this case, there are four state variables and three auxiliary variables.
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # PREAMBLE
            # Define the down_to_stop auxiliary, which is used only in this combination and in combination 7.
            down_to_stop = {}
            for t in time_frame:
                down_to_stop[t] = model.add_continuous_variable(
                    "down_to_stop_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)), 0, 1
                )

            # A. INITIAL CONDITIONS

            # Retrieve the values of the Power attribute over previous_time_frame
            last_power = thermal_unit.power.get_forecast(
                parameters.execution_date, extended_start_date, parameters.start_date - parameters.time_step
            )  # Extract the time series corresponding to the previous period
            last_date = last_power.last_date  # get the last date with a recorded value

            # See if the program needs to be initialized as DayZero or not
            if len(last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif last_date != parameters.start_date - parameters.time_step:
                # last_date doesn't match startDate - TimeStep (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                if parameters.verbose:
                    cfg.logger.warning(
                        "***WARNING***\n The last_date found in Power of equipement {} "
                        "does not match the startDate of the current program. \n "
                        "The program will be initialized as DayZero.".format(thermal_unit.name)
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if parameters.verbose:
                    cfg.logger.info(
                        "Initial conditions of unit {} have been set as in equation (47).".format(thermal_unit.name)
                    )

                for t in previous_time_frame:
                    # Initial conditions on the power output
                    q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    OFF[t] = 1
                    ON_UP[t] = 0
                    ON_DOWN[t] = 0
                    STOP[t] = 0
                    # Initial conditions on the auxiliary variables
                    turned_on[t] = 0
                    turned_off[t] = 0
                    down_to_stop[t] = 0
            else:
                # Initial condition on the power output
                for t in previous_time_frame:
                    q[t] = last_power.get_value(t)

                # Initial conditions on the state variables
                # Only need to set one value, the mutual exclusion constraint being defined over the
                # whole extended time frame.
                for t in previous_time_frame:
                    # There are now three cases : either q_t >= q_min, 0 < q_t < q_min or q_t = 0
                    if last_power.get_value(t) >= thermal_unit.minimum_power.get_value(t):
                        OFF[t] = 0
                        STOP[t] = 0
                        ON_DOWN[t] = 1
                        ON_UP[t] = (
                            1  # Set both ON states to 1 in order to allow the unit to do whatever it wants as there is no
                        )
                        # stable constraint at this point.
                    elif last_power.get_value(t) > 0:
                        STOP[t] = 1
                        OFF[t] = 0
                        ON_UP[t] = 0
                        ON_DOWN[t] = 0
                    else:
                        STOP[t] = 0
                        OFF[t] = 1
                        ON_UP[t] = 0
                        ON_DOWN[t] = 0

                # Initial conditions on the auxiliary variables
                for t in previous_time_frame:
                    # Initialize all the values to 0
                    turned_on[t] = 0
                    turned_off[t] = 0
                    down_to_stop[t] = 0

                    if not t == extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - parameters.time_step
                        # See if the unit has been turned off
                        if STOP[t] - STOP[t_prev] == 1:
                            turned_off[t] = 1
                        # Or turned on
                        elif OFF[t] - OFF[t_prev] == -1:
                            turned_on[t] = 1
                        # Reconstruct down_to_stop
                        elif STOP[t] - ON_DOWN[t_prev] == 0:
                            down_to_stop[t] = 1

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables.

            # Constraints on the indicator that the unit has started on t
            # Enforces eq. (3)
            for t in time_frame:
                model.add_constraint(turned_on[t] <= 1 - OFF[t])
                model.add_constraint(turned_on[t] <= OFF[t - parameters.time_step])
                model.add_constraint(
                    turned_on[t] >= OFF[t - parameters.time_step] - OFF[t],
                    "constraints_defining_turned_on_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Constraints on turned_off
            # Enforces eq. (5) since the STOP state is defined in this case.
            for t in time_frame:
                model.add_constraint(turned_off[t] <= 1 - STOP[t - parameters.time_step])
                model.add_constraint(turned_off[t] <= STOP[t])
                model.add_constraint(
                    turned_off[t] >= STOP[t] - STOP[t - parameters.time_step],
                    "constraints_defining_turned_off_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Constraints on down_to_stop (eq. (20))
            for t in time_frame:
                t_minus_one = t - parameters.time_step
                model.add_constraint(down_to_stop[t] <= STOP[t])
                model.add_constraint(down_to_stop[t] <= ON_DOWN[t_minus_one])
                model.add_constraint(down_to_stop[t] >= STOP[t] + ON_DOWN[t_minus_one] - 1)

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in time_frame:
                # Defined over the whole time frame
                # Enforces eq. (9).
                model.add_constraint(
                    OFF[t] + ON_UP[t] + ON_DOWN[t] + STOP[t] == 1,
                    "mutual_exclusion_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Transitions:
            # Transitions from OFF to STOP and STOP to ON_DOWN and ON_UP are forbidden
            # Direct transitions from ON_UP and ON_DOWN to OFF are forbidden.
            for t in time_frame:
                t_minus_one = t - parameters.time_step
                model.add_constraint(STOP[t_minus_one] + ON_UP[t] <= 1)  # Eq. (13)
                model.add_constraint(STOP[t_minus_one] + ON_DOWN[t] <= 1)  # Eq. (13)
                model.add_constraint(OFF[t_minus_one] + STOP[t] <= 1)  # Eq. (12)
                model.add_constraint(ON_UP[t_minus_one] + OFF[t] <= 1)  # Eq. (18)
                model.add_constraint(
                    ON_DOWN[t_minus_one] + OFF[t] <= 1,
                    "transitions_constraints_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )  # Eq. (18)

            # Eviction constraint : force the unit to remain only T_stop time steps in the shutdown phase.
            for t in time_frame:
                t_minus_T_stop = t - T_stop * parameters.time_step
                # Implement equation (19)
                model.add_constraint(
                    turned_off[t_minus_T_stop] + STOP[t] <= 1,
                    "eviction_constraint_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Mininum time on, minimum time off, minimum time in the STOP state constraints:
            # if T_on >= 2, T_off >= 2 or T_stop >= 2, lock the unit in this state.
            if T_on >= 2:
                for t in time_frame:
                    time_steps = range(1, T_on)  # Corresponds to the set {1,...,T_on - 1}
                    for s in time_steps:
                        # Implement eq. (31), with T_start = 0
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            turned_on[t_minus_s] <= ON_UP[t] + ON_DOWN[t],
                            "minimum_time_ON_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )

            if T_off >= 2:
                for t in time_frame:
                    time_steps = range(1, T_off)  # Corresponds to the set {1,...,T_off - 1}
                    for s in time_steps:
                        # Implement eq. (32) with T_stop > 0
                        t_minus_s_minus_T_stop = (
                            t - s * parameters.time_step - T_stop * parameters.time_step
                        )  # Shift the index because the OFF is formally
                        # considered when entering the STOP state.
                        model.add_constraint(
                            turned_off[t_minus_s_minus_T_stop] <= OFF[t],
                            "minimum_time_OFF_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s_minus_T_stop),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )

            if T_stop >= 2:
                for t in time_frame:
                    for s in stop_time_steps:
                        # Implement eq. (24)
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            turned_off[t_minus_s] <= STOP[t],
                            "shutdown_ramp_of_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Shutdown gradient
            q_min = thermal_unit.minimum_power.max()  # Get the minimumPower without the reserve requirements
            q_step = q_min / T_stop

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))
            for t in time_frame:
                # contractedDifference
                model.add_constraint(contracted_difference_up[t] >= reserves_up_procured.get_value(t) - reserves_up[t])
                model.add_constraint(
                    contracted_difference_down[t] >= reserves_down_procured.get_value(t) - reserves_down[t]
                )
                # automatedContractedDifference
                model.add_constraint(
                    automated_contracted_difference_up[t]
                    >= feasible_automated_reserves_up_procured[t] - automated_reserves_up[t]
                )
                model.add_constraint(
                    automated_contracted_difference_down[t]
                    >= feasible_automated_reserves_down_procured[t] - automated_reserves_down[t]
                )

            # Upward and downward "fill up" constraints.
            for t in time_frame:
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    <= q_upper.get_value(t) + parameters.epsilon
                )  # Upward constraint - eq. (41)
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    >= q_upper.get_value(t) - parameters.epsilon
                )  # Upward constraint - eq. (41)

                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    <= q_lower.get_value(t) + parameters.epsilon
                )  # Downward constraint - eq. (42)
                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    >= q_lower.get_value(t) - parameters.epsilon
                )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            for t in time_frame:
                model.add_constraint(relaxed_reserves[t] <= q_lower.get_value(t) * (1 - ON_UP[t] - ON_DOWN[t]))

            # impossible commitment and stable reserves constraints (eq. (44))
            for t in time_frame:
                model.add_constraint(automated_reserves_up[t] <= maximum_automated * (1 - OFF[t] - STOP[t]))
                model.add_constraint(automated_reserves_down[t] <= maximum_automated * (1 - OFF[t] - STOP[t]))
                model.add_constraint(reserves_up[t] <= q_upper.get_value(t) * (1 - OFF[t] - STOP[t]))
                model.add_constraint(reserves_down[t] <= q_upper.get_value(t) * (1 - OFF[t] - STOP[t]))

            # Power output
            for t in time_frame:
                model.add_constraint(
                    q[t] >= q_lower.get_value(t) * (ON_UP[t] + ON_DOWN[t]) + turned_off[t] * (q_min - q_step),
                    "lower_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Lower bound (eq. 33)
                model.add_constraint(
                    q[t] <= q_upper.get_value(t) * (ON_UP[t] + ON_DOWN[t]) + STOP[t] * q_min - turned_off[t] * q_step,
                    "upper_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Upper bound   (eq.34)

            # Power gradients
            # Definition of the gradients_time_frame : starts at startDate - TimeStep and goes until T-1
            # Gradients are defined on a "shifted" time frame.
            gradients_time_frame = generate_datetimes(
                parameters.start_date - parameters.time_step,
                parameters.end_optimization_date - 2 * parameters.time_step,
                parameters.time_step,
            )

            if delta_q > 0:  # Case where the gradient is finite.
                for t in gradients_time_frame:  # The gradients are defined only up to T-1.
                    t_next = t + parameters.time_step  # Get the next time step
                    # Constrained upward gradient (eq. (35))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= (
                            delta_q * ON_UP[t]
                            - turned_off[t_next] * q_step
                            - STOP[t] * q_step
                            + delta_q_unconstrained * turned_on[t_next]
                        ),
                        "upward_gradient_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                    )  # Upward gradient

                    # Constrained downward gradient (eq. (37))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= (
                            -delta_q * ON_DOWN[t]
                            - turned_off[t_next] * q_step
                            - STOP[t] * q_step
                            + down_to_stop[t_next] * delta_q
                        ),
                        "downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient

            elif delta_q == 0:  # Case where the gradient is 'infinite'
                for t in gradients_time_frame:
                    t_next = t + parameters.time_step  # Get the next time step
                    # Unconstrained upward gradient (eq. (36))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= (
                            delta_q_unconstrained * ON_UP[t]
                            - turned_off[t_next] * q_step
                            - STOP[t] * q_step
                            + delta_q_unconstrained * turned_on[t_next]
                        ),
                        "upward_gradient_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                    )  # Upward gradient

                    # Unconstrained downward gradient (eq. (38))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= (
                            -delta_q_unconstrained * ON_DOWN[t]
                            - turned_off[t_next] * q_step
                            - STOP[t] * q_step
                            + down_to_stop[t_next] * delta_q_unconstrained
                        ),
                        "downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient

            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    "*** WARNING ***\n No gradients have been defined for equipment {}. \n "
                    "Please check the value of `maximum_gradient`.".format(thermal_unit.name)
                )
                raise ValueError("Missing gradients for thermic units.")

                # Energy limits
            if thermal_unit.has_daily_energy_constraint:
                days_in_time_frame = []

                for local_time in time_frame:
                    if datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0) not in days_in_time_frame:
                        days_in_time_frame.append(datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0))

                for date in days_in_time_frame:
                    upper_bound = thermal_unit.maximum_daily_energy.get_value(date)

                    matching_steps = []
                    for local_time in time_frame:
                        if (
                            (local_time.year == date.year)
                            and (local_time.month == date.month)
                            and (local_time.day == date.day)
                        ):
                            matching_steps.append(local_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        model.add_constraint(
                            sum(q[t] for t in matching_steps)
                            <= upper_bound * parameters.time_step / 1440.0 * len(matching_steps),
                            "energy_limit_of_{}_at_{}".format(
                                thermal_unit.name, Utilities.get_date_to_clean_string(date)
                            ),
                        )
                        # TimeStep / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                             #
        #### Combination 3 : T_stop = 0, T_stable >= 1 T_start = 0 ####
        #                                                             #
        # -------------------------------------------------------------#

        if T_stop == 0 and T_start == 0 and T_stable >= 1:
            # In this case, there are four state variables and the following auxiliary variables :
            #     - turned_on[t] and turned_off[t], indicating whether the unit has been turned on or off
            #     - stable[t], indicating whether the unit entered the stable state
            #     - U[t] and D[t], implemented in two stages with tilde_D[t], tilde_D[t] as the first stage
            #     - entered_up[t] and entered_down[t] indicating that the unit entered the UP or down STATE
            #
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # A. INITIAL CONDITIONS

            # Define the startDate - 2 time steps.
            start_date_minus_two = parameters.start_date - 2 * parameters.time_step

            # Retrieve the values of the Power attribute over previous_time_frame
            last_power = thermal_unit.power.get_forecast(
                parameters.execution_date, extended_start_date, parameters.start_date - parameters.time_step
            )  # Extract the time series corresponding to the previous period
            last_date = last_power.last_date  # get the last date with a recorded value

            # See if the program needs to be initialized as DayZero or not
            if len(last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif last_date != parameters.start_date - parameters.time_step:
                # last_date doesn't match startDate - TimeStep (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                if parameters.verbose:
                    cfg.logger.warning(
                        "***WARNING***\n The last_date found in Power of equipement {} "
                        "does not match the startDate of the current program. \n "
                        "The program will be initialized as DayZero.".format(thermal_unit.name)
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if parameters.verbose:
                    cfg.logger.info(
                        "Initial conditions of unit {} have been set as in equation (47).".format(thermal_unit.name)
                    )

                for t in previous_time_frame:
                    # Initial conditions on the power output
                    q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    OFF[t] = 1
                    if not t == start_date_minus_one:
                        ON_UP[t] = 0
                        ON_DOWN[t] = 0
                        ON_FLAT[t] = 0
                        # Initial conditions on the auxiliary variables defined over time_frame_union_minus_one
                        stable[t] = 0
                        entered_up[t] = 0
                        entered_down[t] = 0

                    # Initial conditions on the remaining auxiliary variables
                    turned_on[t] = 0
                    turned_off[t] = 0
            else:
                # Setting up the initial conditions will be a bit more complex. We consecutively do the following:
                #    - Set the inital conditions on the power output
                #    - See wether the unit is ON or OFF
                #    - Initialize the auxiliaries turned_up and turned_down accordingly
                #    - For the steps where the unit is ON:
                #         - See whether the unit was UP, DOWN or FLAT
                #         - Initialize the auxiliary variables accordingly

                # Initial condition on the power output
                for t in previous_time_frame:
                    q[t] = last_power.get_value(t)

                # Initial conditions on the state variables OFF/ON
                for t in previous_time_frame:
                    if last_power.get_value(t) > 0:
                        OFF[t] = 0  # Only the OFF variable is initialized. ON_FLAT, ON_DOWN and ON_UP will be
                        # initialized afterwards.
                    else:
                        OFF[t] = 1
                        if not t == start_date_minus_one:
                            ON_UP[t] = 0
                            ON_DOWN[t] = 0
                            ON_FLAT[t] = 0

                # Initial conditions on the auxiliary variables turned_on and turned_off
                for t in previous_time_frame:
                    # Initialize all the values to 0
                    turned_on[t] = 0
                    turned_off[t] = 0
                    if not t == extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - parameters.time_step
                        # See if the unit has been turned off
                        if OFF[t] - OFF[t_prev] == 1:
                            turned_off[t] = 1
                        # Or turned on
                        elif OFF[t] - OFF[t_prev] == -1:
                            turned_on[t] = 1

                # Reconstruct the values of UP, DOWN and FLAT and their associated
                # auxiliary variables
                for t in previous_time_frame[
                    :-1
                ]:  # Loop excluding last date because we are reconstructing the values of the
                    # ON variables using  variations between q[t] and q[t-1].

                    t_prev = t - parameters.time_step
                    if OFF[t_prev] == 0:
                        # See if the power output was stable, increasing or decreasing:
                        if q[t] > q[t_prev]:  # Recall that here t_prev is earlier than t.
                            ON_UP[t_prev] = 1
                            ON_DOWN[t_prev] = 0
                            ON_FLAT[t_prev] = 0
                        elif q[t] < q[t_prev]:
                            ON_UP[t_prev] = 0
                            ON_DOWN[t_prev] = 1
                            ON_FLAT[t_prev] = 0
                        elif q[t] == q[t_prev]:
                            ON_UP[t_prev] = 0
                            ON_DOWN[t_prev] = 0
                            ON_FLAT[t_prev] = 1

                # Initialize the auxiliary variables
                for t in previous_time_frame[
                    1:
                ]:  # Loop excluding start_date_minus_one, which is the first element in the previous_time_frame list.
                    # Default value set to 0
                    stable[t] = 0
                    entered_up[t] = 0
                    entered_down[t] = 0

                    if (not t == extended_start_date) and (not OFF[t] == 1):
                        t_prev = t - parameters.time_step

                        # See if the unit entered the FLAT state
                        if ON_FLAT[t] - ON_FLAT[t_prev] == 1:
                            stable[t] = 1
                        # or the UP state
                        if ON_UP[t] - ON_UP[t_prev] == 1:
                            entered_up[t] = 1
                        # or the DOWN state
                        if ON_DOWN[t] - ON_DOWN[t_prev] == 1:
                            entered_down[t] = 1

                            # Initialize the gradient auxiliaries. This is only required for the last time step of the
            # previous_time_frame. Only ON_UP[start_date_minus_one] and ON_DOWN[start_date_minus_one] are decision variables
            # in the expressions below.
            U[start_date_minus_one] = (
                ON_UP[start_date_minus_one]
                * ON_UP[start_date_minus_two]
                * (q[start_date_minus_one] - q[start_date_minus_two])
            )
            D[start_date_minus_one] = (
                ON_DOWN[start_date_minus_one]
                * ON_DOWN[start_date_minus_two]
                * (q[start_date_minus_one] - q[start_date_minus_two])
            )

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them : turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t (turned_on, sec. 6.1.1)
            # Enforces eq. (3)
            for t in time_frame:
                model.add_constraint(turned_on[t] <= 1 - OFF[t])
                model.add_constraint(turned_on[t] <= OFF[t - parameters.time_step])
                model.add_constraint(turned_on[t] >= OFF[t - parameters.time_step] - OFF[t])

                # Constraints on turned_off
            # Enforces eq. (4) as there is no STOP state in this case.
            for t in time_frame:
                model.add_constraint(turned_off[t] <= 1 - OFF[t - parameters.time_step])
                model.add_constraint(turned_off[t] <= OFF[t])
                model.add_constraint(turned_off[t] >= OFF[t] - OFF[t - parameters.time_step])

            # stable auxiliary variable
            # Enforces eq. (6)
            for t in time_frame_union_minus_one:
                model.add_constraint(stable[t] <= 1 - ON_FLAT[t - parameters.time_step])
                model.add_constraint(stable[t] <= ON_FLAT[t])
                model.add_constraint(stable[t] >= ON_FLAT[t] - ON_FLAT[t - parameters.time_step])

            # entered_up and entered_down auxiliaries
            for t in time_frame_union_minus_one:
                # entered_up (eq. (7))
                model.add_constraint(entered_up[t] <= 1 - ON_UP[t - parameters.time_step])
                model.add_constraint(entered_up[t] <= ON_UP[t])
                model.add_constraint(entered_up[t] >= ON_UP[t] - ON_UP[t - parameters.time_step])
                # entered_down (eq. (8))
                model.add_constraint(entered_down[t] <= 1 - ON_DOWN[t - parameters.time_step])
                model.add_constraint(entered_down[t] <= ON_DOWN[t])
                model.add_constraint(entered_down[t] >= ON_DOWN[t] - ON_DOWN[t - parameters.time_step])

            # UP and DOWN auxiliary variables for the gradient.
            # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
            # power output twice in a row, then the second time the gradient is locked.
            # In practice, these variables are defined in two stages

            # First stage : tilde_U and tilde_D
            for t in time_frame:  # Loop in all the time_frame but startDate.
                t_minus_one = t - parameters.time_step
                # tilde_U (eq. (28))
                model.add_constraint(tilde_U[t] <= Q_max * ON_UP[t_minus_one])
                model.add_constraint(tilde_U[t] >= Q_min * ON_UP[t_minus_one])
                model.add_constraint(tilde_U[t] <= q[t] - q[t_minus_one] - Q_min * (1 - ON_UP[t_minus_one]))
                model.add_constraint(
                    tilde_U[t] >= q[t] - q[t_minus_one] - Q_max * (1 - ON_UP[t_minus_one]),
                    "VALUE_of_tilde_UP_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

                # tilde_D (eq. (30))
                model.add_constraint(tilde_D[t] <= Q_max * ON_DOWN[t_minus_one])
                model.add_constraint(tilde_D[t] >= Q_min * ON_DOWN[t_minus_one])
                model.add_constraint(tilde_D[t] <= q[t] - q[t_minus_one] - Q_min * (1 - ON_DOWN[t_minus_one]))
                model.add_constraint(
                    tilde_D[t] >= q[t] - q[t_minus_one] - Q_max * (1 - ON_DOWN[t_minus_one]),
                    "VALUE_of_tilde_DOWN_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Second stage : U and D
            # These variables wil be added to the gradient constraints.
            for t in time_frame:
                # U (eq. (27))
                model.add_constraint(U[t] <= Q_max * ON_UP[t])
                model.add_constraint(U[t] >= Q_min * ON_UP[t])
                model.add_constraint(U[t] <= tilde_U[t] - Q_min * (1 - ON_UP[t]))
                model.add_constraint(
                    U[t] >= tilde_U[t] - Q_max * (1 - ON_UP[t]),
                    "VALUE_of_UP_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )
                # D (eq. (29))
                model.add_constraint(D[t] <= Q_max * ON_DOWN[t])
                model.add_constraint(D[t] >= Q_min * ON_DOWN[t])
                model.add_constraint(D[t] <= tilde_D[t] - Q_min * (1 - ON_DOWN[t]))
                model.add_constraint(
                    D[t] >= tilde_D[t] - Q_max * (1 - ON_DOWN[t]),
                    "VALUE_of_DOWN_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

                # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in time_frame_union_minus_one:
                # Defined over the whole time frame.
                # Enforces eq. (9)
                model.add_constraint(
                    OFF[t] + ON_UP[t] + ON_DOWN[t] + ON_FLAT[t] == 1,
                    "mutual_exclusion_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Transitions:
            # UP-DOWN and DOWN-UP transitions are forbidden.
            for t in time_frame_union_minus_one:
                t_minus_one = t - parameters.time_step
                # Implement eq. (25).
                model.add_constraint(ON_UP[t_minus_one] + ON_DOWN[t] <= 1)
                model.add_constraint(
                    ON_DOWN[t_minus_one] + ON_UP[t] <= 1,
                    "transitions_constraints_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Mininum time on and minimum time off constraints:
            # if T_on >= 2 or T_off >= 2 or T_stable >= 2, lock the unit in this state.
            if T_on >= 2:
                for t in time_frame_union_minus_one:
                    time_steps = range(1, T_on)  # Corresponds to the set {1,..., T_on - 1}
                    for s in time_steps:
                        # Enforces eq. (31), with T_start = 0
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            turned_on[t_minus_s] <= ON_UP[t] + ON_DOWN[t] + ON_FLAT[t],
                            "minimum_time_ON_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_off >= 2:
                for t in time_frame:
                    time_steps = range(1, T_off)  # Corresponds to the set {1,..., T_off - 1}
                    for s in time_steps:
                        # Enforces eq. (32) with T_stop = 0
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            turned_off[t_minus_s] <= OFF[t],
                            "minimum_time_OFF_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_stable >= 2:
                for t in time_frame_union_minus_one:
                    time_steps = range(1, T_stable - 1)  # Corresponds to the set {1,..., T_stable - 2}
                    for s in time_steps:
                        # Enforces eq. (26)
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            stable[t_minus_s] <= ON_FLAT[t],
                            "minimum_time_STABLE_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Reserves requirements
            # We are in a case where there is a FLAT state, so manual reserves can only be provided
            # when the unit is in the FLAT state.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))
            for t in time_frame:
                # contractedDifference
                model.add_constraint(contracted_difference_up[t] >= reserves_up_procured.get_value(t) - reserves_up[t])
                model.add_constraint(
                    contracted_difference_down[t] >= reserves_down_procured.get_value(t) - reserves_down[t]
                )
                # automatedContractedDifference
                model.add_constraint(
                    automated_contracted_difference_up[t]
                    >= feasible_automated_reserves_up_procured[t] - automated_reserves_up[t]
                )
                model.add_constraint(
                    automated_contracted_difference_down[t]
                    >= feasible_automated_reserves_down_procured[t] - automated_reserves_down[t]
                )

            # Upward and downward "fill up" constraints.
            for t in time_frame:
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    <= q_upper.get_value(t) + parameters.epsilon
                )  # Upward constraint - eq. (41)
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    >= q_upper.get_value(t) - parameters.epsilon
                )  # Upward constraint - eq. (41)

                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    <= q_lower.get_value(t) + parameters.epsilon
                )  # Downward constraint - eq. (42)
                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    >= q_lower.get_value(t) - parameters.epsilon
                )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            for t in time_frame:
                model.add_constraint(
                    relaxed_reserves[t] <= q_lower.get_value(t) * (1 - ON_UP[t] - ON_FLAT[t] - ON_DOWN[t])
                )

            # impossible commitment and stable reserves constraints (eqs. (44) and (45))
            for t in time_frame:
                model.add_constraint(automated_reserves_up[t] <= maximum_automated * (1 - OFF[t]))
                model.add_constraint(automated_reserves_down[t] <= maximum_automated * (1 - OFF[t]))
                model.add_constraint(
                    reserves_up[t] <= q_upper.get_value(t) * (1 - ON_UP[t] - ON_DOWN[t] - OFF[t])
                )  # for compacity, implements both eq (44) and (45)
                model.add_constraint(reserves_down[t] <= q_upper.get_value(t) * (1 - ON_UP[t] - ON_DOWN[t] - OFF[t]))

            # Power output
            for t in time_frame:
                model.add_constraint(
                    q[t] >= q_lower.get_value(t) * (ON_UP[t] + ON_DOWN[t] + ON_FLAT[t]),
                    "lower_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Lower bound (eq. (33))

                model.add_constraint(
                    q[t] <= q_upper.get_value(t) * (ON_UP[t] + ON_DOWN[t] + ON_FLAT[t]),
                    "upper_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Upper bound (eq. (34))

            # Power gradients
            # Definition of the gradients_time_frame : starts at startDate - TimeStep and goes until T-1
            # Gradients are defined on a "shifted" time frame.
            gradients_time_frame = generate_datetimes(
                parameters.start_date - parameters.time_step,
                parameters.end_optimization_date - 2 * parameters.time_step,
                parameters.time_step,
            )

            if delta_q > 0:  # Case where the gradient is finite.
                for t in gradients_time_frame:  # The gradients are defined only up to T-1.
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. (35))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= delta_q * entered_up[t] + U[t] + D[t] + delta_q_unconstrained * turned_on[t_next],
                        "upward_gradient_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                    )  # Upward gradient

                    # Downard constrained gradient (eq. (37))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= -delta_q * entered_down[t] + U[t] + D[t] - delta_q_unconstrained * turned_off[t_next],
                        "downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient

            elif delta_q == 0:  # Case where the gradient is 'infinite'
                for t in gradients_time_frame:
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward unconstrained gradient (eq. (36))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= delta_q_unconstrained * entered_up[t]
                        + U[t]
                        + D[t]
                        + delta_q_unconstrained * turned_on[t_next],
                        "unconstrained_upward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (38))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= -delta_q_unconstrained * entered_down[t]
                        + U[t]
                        + D[t]
                        - delta_q_unconstrained * turned_off[t_next],
                        "unconstrained_downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient

            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    "*** WARNING ***\n No gradients have been defined for equipment {}. \n "
                    "Please check the value of `maximum_gradient`.".format(thermal_unit.name)
                )
                raise ValueError("Missing gradients for thermic units.")

                # Energy limits
            if thermal_unit.has_daily_energy_constraint:
                days_in_time_frame = []

                for local_time in time_frame:
                    if datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0) not in days_in_time_frame:
                        days_in_time_frame.append(datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0))

                for date in days_in_time_frame:
                    upper_bound = thermal_unit.maximum_daily_energy.get_value(date)

                    matching_steps = []
                    for local_time in time_frame:
                        if (
                            (local_time.year == date.year)
                            and (local_time.month == date.month)
                            and (local_time.day == date.day)
                        ):
                            matching_steps.append(local_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        model.add_constraint(
                            sum(q[t] for t in matching_steps)
                            <= upper_bound * parameters.time_step / 1440.0 * len(matching_steps),
                            "energy_limit_of_{}_at_{}".format(
                                thermal_unit.name, Utilities.get_date_to_clean_string(date)
                            ),
                        )
                        # TimeStep / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                             #
        ##### Combination 4 : T_start >= 1, T_stable = T_stop = 0 #####
        #                                                             #
        # -------------------------------------------------------------#

        if T_start >= 1 and T_stop == 0 and T_stable == 0:
            # In this case, there are four state variables and two auxiliary variables.
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # A. INITIAL CONDITIONS

            # Retrieve the values of the Power attribute over previous_time_frame
            last_power = thermal_unit.power.get_forecast(
                parameters.execution_date, extended_start_date, parameters.start_date - parameters.time_step
            )  # Extract the time series corresponding to the previous period
            last_date = last_power.last_date  # get the last date with a recorded value

            # See if the program needs to be initialized as DayZero or not
            if len(last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif last_date != parameters.start_date - parameters.time_step:
                # last_date doesn't match startDate - TimeStep (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                if parameters.verbose:
                    cfg.logger.warning(
                        "***WARNING***\n The last_date found in Power of equipement {} "
                        "does not match the startDate of the current program. \n "
                        "The program will be initialized as DayZero.".format(thermal_unit.name)
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if parameters.verbose:
                    cfg.logger.info(
                        "Initial conditions of unit {} have been set as in equation (47).".format(thermal_unit.name)
                    )

                for t in previous_time_frame:
                    # Initial conditions on the power output
                    q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    OFF[t] = 1
                    ON_UP[t] = 0
                    ON_DOWN[t] = 0
                    START[t] = 0
                    # Initial conditions on the auxiliary variables
                    turned_on[t] = 0
                    turned_off[t] = 0
            else:
                # Initial condition on the power output
                for t in previous_time_frame:
                    q[t] = last_power.get_value(t)

                # Initial conditions on the state variables
                for t in previous_time_frame:
                    # There are now three cases : either q_t >= q_min, 0 < q_t < q_min or q_t = 0
                    if last_power.get_value(t) >= thermal_unit.minimum_power.get_value(t):
                        OFF[t] = 0
                        START[t] = 0
                        ON_DOWN[t] = 1
                        ON_UP[t] = (
                            1  # Set both ON states to 1 in order to allow the unit to do whatever it wants as there is no
                        )
                        # stable constraint at this point.
                    elif last_power.get_value(t) > 0:
                        START[t] = 1
                        OFF[t] = 0
                        ON_UP[t] = 0
                        ON_DOWN[t] = 0
                    else:
                        START[t] = 0
                        OFF[t] = 1
                        ON_UP[t] = 0
                        ON_DOWN[t] = 0

                # Initial conditions on the auxiliary variables
                for t in previous_time_frame:
                    # Initialize all the values to 0
                    turned_on[t] = 0
                    turned_off[t] = 0
                    if not t == extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - parameters.time_step
                        # See if the unit has been turned off
                        if OFF[t] - OFF[t_prev] == 1:
                            turned_off[t] = 1
                        # Or turned on
                        elif START[t] - START[t_prev] == 1:
                            turned_on[t] = 1

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables, turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # which is detected when OFF[t-1] = 1 and OFF[t] = 0
            # This amounts to be turned on when the unit enters the START state as in eq. (3)
            for t in time_frame:
                model.add_constraint(turned_on[t] <= 1 - OFF[t])
                model.add_constraint(turned_on[t] <= OFF[t - parameters.time_step])
                model.add_constraint(
                    turned_on[t] >= OFF[t - parameters.time_step] - OFF[t],
                    "constraints_defining_turned_on_{}".format(Utilities.get_date_to_clean_string(t)),
                )

                # Constraints on turned_off
            # Defined here when entering the OFF state as in eq. (4) because T_stop = 0
            for t in time_frame:
                model.add_constraint(turned_off[t] <= 1 - OFF[t - parameters.time_step])
                model.add_constraint(turned_off[t] <= OFF[t])
                model.add_constraint(
                    turned_off[t] >= OFF[t] - OFF[t - parameters.time_step],
                    "constraints_defining_turned_off_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in time_frame:
                # Defined over the whole time frame
                # Enforces eq. (9)
                model.add_constraint(
                    OFF[t] + ON_UP[t] + ON_DOWN[t] + START[t] == 1,
                    "mutual_exclusion_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Transitions:
            # Transitions from ON_UP and ON_DOWN to START and START to OFF are forbidden
            # Direct transitions from OFF to ON_UP and ON_DOWN are forbidden.
            for t in time_frame:
                t_minus_one = t - parameters.time_step
                model.add_constraint(ON_UP[t_minus_one] + START[t] <= 1)  # eq. (10)
                model.add_constraint(ON_DOWN[t_minus_one] + START[t] <= 1)  # eq. (10)
                model.add_constraint(START[t_minus_one] + OFF[t] <= 1)  # eq. (11)
                model.add_constraint(OFF[t_minus_one] + ON_UP[t] <= 1)  # eq. (15)
                model.add_constraint(
                    OFF[t_minus_one] + ON_DOWN[t] <= 1,
                    "transitions_constraints_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )  # eq. (15)

            # Eviction constraint. This constraint forces the unit to leave the START state once the startup phase is finished.
            for t in time_frame:
                t_minus_T_start = t - T_start * parameters.time_step
                # Implement eqution (16)
                model.add_constraint(
                    turned_on[t_minus_T_start] + START[t] <= 1,
                    "eviction_constraint_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Mininum time on and minimum time off constraints:
            # if T_on >= 2, T_off >= 2 or T_stop >= 2, lock the unit in this state.
            if T_on >= 2:
                for t in time_frame:
                    time_steps = range(1, T_on)
                    for s in time_steps:
                        # Enforce eq. (31) with T_start > 0
                        t_minus_s_minus_T_start = t - s * parameters.time_step - T_start * parameters.time_step
                        model.add_constraint(
                            turned_on[t_minus_s_minus_T_start] <= ON_UP[t] + ON_DOWN[t],
                            "minimum_time_ON_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s_minus_T_start),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_off >= 2:
                for t in time_frame:
                    time_steps = range(1, T_off)
                    for s in time_steps:
                        # Enforce eq. (32) with T_stop = 0
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            turned_off[t_minus_s] <= OFF[t],
                            "minimum_time_OFF_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_start >= 2:
                for t in time_frame:
                    for s in start_time_steps:
                        t_minus_s = t - s * parameters.time_step
                        # Enforce eq. (17)
                        model.add_constraint(
                            turned_on[t_minus_s] <= START[t],
                            "startup_ramp_of_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Start-up gradient
            q_min = thermal_unit.minimum_power.max()  # Get the minimumPower without the reserve requirements
            q_step = q_min / T_start

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))
            for t in time_frame:
                # contractedDifference
                model.add_constraint(contracted_difference_up[t] >= reserves_up_procured.get_value(t) - reserves_up[t])
                model.add_constraint(
                    contracted_difference_down[t] >= reserves_down_procured.get_value(t) - reserves_down[t]
                )
                # automatedContractedDifference
                model.add_constraint(
                    automated_contracted_difference_up[t]
                    >= feasible_automated_reserves_up_procured[t] - automated_reserves_up[t]
                )
                model.add_constraint(
                    automated_contracted_difference_down[t]
                    >= feasible_automated_reserves_down_procured[t] - automated_reserves_down[t]
                )

            # Upward and downward "fill up" constraints.
            for t in time_frame:
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    <= q_upper.get_value(t) + parameters.epsilon
                )  # Upward constraint - eq. (41)
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    >= q_upper.get_value(t) - parameters.epsilon
                )  # Upward constraint - eq. (41)

                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    <= q_lower.get_value(t) + parameters.epsilon
                )  # Downward constraint - eq. (42)
                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    >= q_lower.get_value(t) - parameters.epsilon
                )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            for t in time_frame:
                model.add_constraint(relaxed_reserves[t] <= q_lower.get_value(t) * (1 - ON_UP[t] - ON_DOWN[t]))

            # impossible commitment and stable reserves constraints (eq. (44))
            for t in time_frame:
                model.add_constraint(automated_reserves_up[t] <= maximum_automated * (1 - OFF[t] - START[t]))
                model.add_constraint(automated_reserves_down[t] <= maximum_automated * (1 - OFF[t] - START[t]))
                model.add_constraint(reserves_up[t] <= q_upper.get_value(t) * (1 - OFF[t] - START[t]))
                model.add_constraint(reserves_down[t] <= q_upper.get_value(t) * (1 - OFF[t] - START[t]))

            # Power output
            for t in time_frame:
                model.add_constraint(
                    q[t] >= q_lower.get_value(t) * (ON_UP[t] + ON_DOWN[t]),
                    "lower_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Lower bound (eq. (33))
                model.add_constraint(
                    q[t] <= q_upper.get_value(t) * (ON_UP[t] + ON_DOWN[t]) + START[t] * q_min,
                    "upper_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Upper bound (eq. (34))

            # Power gradients
            # Definition of the gradients_time_frame : starts at startDate - TimeStep and goes until T-1
            # Gradients are defined on a "shifted" time frame.
            gradients_time_frame = generate_datetimes(
                parameters.start_date - parameters.time_step,
                parameters.end_optimization_date - 2 * parameters.time_step,
                parameters.time_step,
            )

            if delta_q > 0:  # Case where the gradient is finite.
                for t in gradients_time_frame:  # The gradients are defined only up to T-1.
                    # NB. The downward gradient implemented here requires the unit to be at most at deltaQ in order to be able to enter the stop state.
                    # The resulting constraint set is considerably more constraining than if the gradient was relaxed.
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. (35))
                    model.add_constraint(
                        q[t_next] - q[t] <= delta_q * ON_UP[t] + turned_on[t_next] * q_step + START[t] * q_step,
                        "upward_gradient_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (37))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= -delta_q * ON_DOWN[t]
                        + turned_on[t_next] * q_step
                        + START[t] * q_step
                        - delta_q_unconstrained * turned_off[t_next],
                        "downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient

            elif delta_q == 0:  # Case where the gradient is 'infinite'
                for t in gradients_time_frame:
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward unconstrained gradient (eq. (36))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= delta_q_unconstrained * ON_UP[t] + turned_on[t_next] * q_step + START[t] * q_step,
                        "unconstrained_upward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (38))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= (
                            -delta_q_unconstrained * ON_DOWN[t]
                            + turned_on[t_next] * q_step
                            + START[t] * q_step
                            - delta_q_unconstrained * turned_off[t_next]
                        ),
                        "unconstrained_downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient
            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    "*** WARNING ***\n No gradients have been defined for equipment {}. \n "
                    "Please check the value of `maximum_gradient`.".format(thermal_unit.name)
                )
                raise ValueError("Missing gradients for thermic units.")

                # Energy limits
            if thermal_unit.has_daily_energy_constraint:
                days_in_time_frame = []

                for local_time in time_frame:
                    if datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0) not in days_in_time_frame:
                        days_in_time_frame.append(datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0))

                for date in days_in_time_frame:
                    upper_bound = thermal_unit.maximum_daily_energy.get_value(date)

                    matching_steps = []
                    for local_time in time_frame:
                        if (
                            (local_time.year == date.year)
                            and (local_time.month == date.month)
                            and (local_time.day == date.day)
                        ):
                            matching_steps.append(local_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        model.add_constraint(
                            sum(q[t] for t in matching_steps)
                            <= upper_bound * parameters.time_step / 1440.0 * len(matching_steps),
                            "energy_limit_of_{}_at_{}".format(
                                thermal_unit.name, Utilities.get_date_to_clean_string(date)
                            ),
                        )
                        # TimeStep / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                             #
        ###   Combination 5 : T_start =0, T_stable = T_stop >= 1    ###
        #                                                             #
        # -------------------------------------------------------------#

        if T_stop >= 1 and T_start == 0 and T_stable >= 1:
            # In this case, there are four state variables and the following auxiliary variables :
            #     - turned_on[t] and turned_off[t], indicating whether the unit has been turned on or off
            #     - stable[t], indicating whether the unit entered the stable state
            #     - U[t] and D[t], implemented in two stages with tilde_D[t], tilde_D[t] as the first stage
            #     - entered_up[t] and entered_down[t] indicating that the unit entered the UP or down STATE
            #
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # PREAMBLE
            # Definition of two additional auxiliary variables needed specifically to handle this case,
            # flat_down_stop, which detects when the unit follows a FLAT(t-2) - DOWN(t-1) and STOP(t) path
            # and DD, which detects if the unit is to be stopped at t+1 (i.e. STOP(t+1) = 1) after having been
            # in the DOWN state at time steps t and t-1.

            # flat_down_stop
            flat_down_stop = {}
            for t in time_frame:
                flat_down_stop[t] = model.add_continuous_variable(
                    "flat_down_stop_at_{}_equip_{}".format(Utilities.get_date_to_clean_string(t), thermal_unit.name),
                    0,
                    1,
                )

            # DD
            # Definition of the gradients_time_frame : starts at startDate - TimeStep and goes until T-1
            # Gradients are defined on a "shifted" time frame.
            gradients_time_frame = generate_datetimes(
                parameters.start_date - parameters.time_step,
                parameters.end_optimization_date - 2 * parameters.time_step,
                parameters.time_step,
            )

            DD = {}
            for t in gradients_time_frame:
                DD[t] = model.add_continuous_variable(
                    "DD_at_{}_equip_{}".format(Utilities.get_date_to_clean_string(t), thermal_unit.name), Q_min, Q_max
                )

            # A. INITIAL CONDITIONS

            # Define the startDate - 2 time steps.
            start_date_minus_two = parameters.start_date - 2 * parameters.time_step

            # Retrieve the values of the Power attribute over previous_time_frame
            last_power = thermal_unit.power.get_forecast(
                parameters.execution_date, extended_start_date, parameters.start_date - parameters.time_step
            )  # Extract the time series corresponding to the previous period
            last_date = last_power.last_date  # get the last date with a recorded value

            # See if the program needs to be initialized as DayZero or not
            if len(last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif last_date != parameters.start_date - parameters.time_step:
                # last_date doesn't match startDate - TimeStep (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                if parameters.verbose:
                    cfg.logger.warning(
                        "***WARNING***\n The last_date found in Power of equipement {} "
                        "does not match the startDate of the current program. \n "
                        "The program will be initialized as DayZero.".format(thermal_unit.name)
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if parameters.verbose:
                    cfg.logger.info(
                        "Initial conditions of unit {} have been set as in equation (47).".format(thermal_unit.name)
                    )

                for t in previous_time_frame:
                    # Initial conditions on the power output
                    q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    OFF[t] = 1
                    STOP[t] = 0
                    if not t == start_date_minus_one:
                        ON_UP[t] = 0
                        ON_DOWN[t] = 0
                        ON_FLAT[t] = 0
                        # Initial conditions on the auxiliary variables defined over time_frame_union_minus_one
                        stable[t] = 0
                        entered_up[t] = 0
                        entered_down[t] = 0

                    # Initial conditions on the remaining auxiliary variables
                    turned_on[t] = 0
                    turned_off[t] = 0
                    flat_down_stop[t] = 0
            else:
                # Setting up the initial conditions will be a bit more complex. We consecutively do the following:
                #    - Set the inital conditions on the power output
                #    - See wether the unit is ON or OFF
                #    - Initialize the auxiliaries turned_up and turned_down accordingly
                #    - For the steps where the unit is ON:
                #         - See whether the unit was UP, DOWN or FLAT
                #         - Initialize the auxiliary variables accordingly

                # Initial condition on the power output
                for t in previous_time_frame:
                    q[t] = last_power.get_value(t)

                # Initial conditions on the state variables OFF/ON
                for t in previous_time_frame:
                    if last_power.get_value(t) >= thermal_unit.minimum_power.get_value(t):
                        OFF[t] = (
                            0  # Only the OFF and STOP variables are initialized. ON_FLAT, ON_DOWN and ON_UP will be
                        )
                        # initialized afterwards.
                        STOP[t] = 0
                    elif last_power.get_value(t) > 0:
                        OFF[t] = 0
                        STOP[t] = 1
                        if not t == start_date_minus_one:
                            ON_UP[t] = 0
                            ON_DOWN[t] = 0
                            ON_FLAT[t] = 0
                    else:
                        OFF[t] = 1
                        STOP[t] = 0
                        if not t == start_date_minus_one:
                            ON_UP[t] = 0
                            ON_DOWN[t] = 0
                            ON_FLAT[t] = 0

                # Initial conditions on the auxiliary variables turned_on turned_off and flat_down_stop
                for t in previous_time_frame:
                    # Initialize all the values to 0
                    turned_on[t] = 0
                    turned_off[t] = 0
                    flat_down_stop[t] = 0
                    if not t == extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - parameters.time_step
                        # See if the unit has been turned off
                        if STOP[t] - STOP[t_prev] == 1:
                            turned_off[t] = 1
                        # Or turned on
                        elif OFF[t] - OFF[t_prev] == -1:
                            turned_on[t] = 1

                # Reconstruct the values of UP, DOWN and FLAT and their associated
                # auxiliary variables
                for t in previous_time_frame[
                    :-1
                ]:  # Loop excluding last date because we are reconstructing the values of the
                    # ON variables using  variations between q[t] and q[t-1].

                    t_prev = t - parameters.time_step
                    if OFF[t_prev] == 0:
                        # See if the power output was stable, increasing or decreasing:
                        if q[t] > q[t_prev]:  # Recall that here t_prev is earlier than t.
                            ON_UP[t_prev] = 1
                            ON_DOWN[t_prev] = 0
                            ON_FLAT[t_prev] = 0
                        elif q[t] < q[t_prev]:
                            ON_UP[t_prev] = 0
                            ON_DOWN[t_prev] = 1
                            ON_FLAT[t_prev] = 0
                        elif q[t] == q[t_prev]:
                            ON_UP[t_prev] = 0
                            ON_DOWN[t_prev] = 0
                            ON_FLAT[t_prev] = 1

                # Initialize the auxiliary variables
                for t in previous_time_frame[
                    1:
                ]:  # Loop excluding start_date_minus_one, which is the first element in the previous_time_frame list.
                    # Default value set to 0
                    stable[t] = 0
                    entered_up[t] = 0
                    entered_down[t] = 0

                    if (not t == extended_start_date) and (not OFF[t] == 1):
                        t_prev = t - parameters.time_step

                        # See if the unit entered the FLAT state
                        if ON_FLAT[t] - ON_FLAT[t_prev] == 1:
                            stable[t] = 1
                        # or the UP state
                        if ON_UP[t] - ON_UP[t_prev] == 1:
                            entered_up[t] = 1
                        # or the DOWN state
                        if ON_DOWN[t] - ON_DOWN[t_prev] == 1:
                            entered_down[t] = 1

                # Initialize flat_down_stop.
                for t in previous_time_frame[:-2]:
                    # Moreover, if we are after extended_start_date + TimeStep
                    # initialize flat_down_stop (which traces back up to two time index before)
                    t_minus_one = t - parameters.time_step
                    t_minus_two = t - 2 * parameters.time_step
                    flat_down_stop[t] = int(math.floor((STOP[t] + ON_DOWN[t_minus_one] + ON_FLAT[t_minus_two]) / 3))

                    # Initialize the gradient auxiliaries. This is only required for the last time step of the
            # previous_time_frame. Only ON_UP[start_date_minus_one] and ON_DOWN[start_date_minus_one] are decision variables
            # in the expressions below.
            U[start_date_minus_one] = (
                ON_UP[start_date_minus_one]
                * ON_UP[start_date_minus_two]
                * (q[start_date_minus_one] - q[start_date_minus_two])
            )
            D[start_date_minus_one] = (
                ON_DOWN[start_date_minus_one]
                * ON_DOWN[start_date_minus_two]
                * (q[start_date_minus_one] - q[start_date_minus_two])
            )

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them : turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Enforces eq. (3)
            for t in time_frame:
                model.add_constraint(turned_on[t] <= 1 - OFF[t])
                model.add_constraint(turned_on[t] <= OFF[t - parameters.time_step])
                model.add_constraint(turned_on[t] >= OFF[t - parameters.time_step] - OFF[t])

                # Constraints on turned_off
            # Enforces eq. (5) as there a STOP state in this case.
            for t in time_frame:
                model.add_constraint(turned_off[t] <= 1 - STOP[t - parameters.time_step])
                model.add_constraint(turned_off[t] <= STOP[t])
                model.add_constraint(turned_off[t] >= STOP[t] - STOP[t - parameters.time_step])

            # stable auxiliary variable
            # Enforces eq. (6)
            for t in time_frame_union_minus_one:
                model.add_constraint(stable[t] <= 1 - ON_FLAT[t - parameters.time_step])
                model.add_constraint(stable[t] <= ON_FLAT[t])
                model.add_constraint(stable[t] >= ON_FLAT[t] - ON_FLAT[t - parameters.time_step])

            # flat_down_stop auxiliary (eq. (22))
            for t in time_frame:
                t_minus_one = t - parameters.time_step
                t_minus_two = t - 2 * parameters.time_step
                model.add_constraint(flat_down_stop[t] <= STOP[t])
                model.add_constraint(flat_down_stop[t] <= ON_DOWN[t_minus_one])
                model.add_constraint(flat_down_stop[t] <= ON_FLAT[t_minus_two])
                model.add_constraint(flat_down_stop[t] >= STOP[t] + ON_DOWN[t_minus_one] + ON_FLAT[t_minus_two] - 2)

            # entered_up and entered_down auxiliaries
            for t in time_frame_union_minus_one:
                # entered_up (eq. (7))
                model.add_constraint(entered_up[t] <= 1 - ON_UP[t - parameters.time_step])
                model.add_constraint(entered_up[t] <= ON_UP[t])
                model.add_constraint(entered_up[t] >= ON_UP[t] - ON_UP[t - parameters.time_step])
                # entered_down (eq. (8))
                model.add_constraint(entered_down[t] <= 1 - ON_DOWN[t - parameters.time_step])
                model.add_constraint(entered_down[t] <= ON_DOWN[t])
                model.add_constraint(entered_down[t] >= ON_DOWN[t] - ON_DOWN[t - parameters.time_step])

            # UP and DOWN auxiliary variables for the gradient.
            # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
            # power output twice in a row, then the second time the gradient is locked.
            # In practice, these variables are defined in two stages

            # First stage : tilde_U and tilde_D
            for t in time_frame:  # Loop in all the time_frame but startDate.
                t_minus_one = t - parameters.time_step
                # tilde_U (eq. (28))
                model.add_constraint(tilde_U[t] <= Q_max * ON_UP[t_minus_one])
                model.add_constraint(tilde_U[t] >= Q_min * ON_UP[t_minus_one])
                model.add_constraint(tilde_U[t] <= q[t] - q[t_minus_one] - Q_min * (1 - ON_UP[t_minus_one]))
                model.add_constraint(
                    tilde_U[t] >= q[t] - q[t_minus_one] - Q_max * (1 - ON_UP[t_minus_one]),
                    "VALUE_of_tilde_UP_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

                # tilde_D (eq. (30))
                model.add_constraint(tilde_D[t] <= Q_max * ON_DOWN[t_minus_one])
                model.add_constraint(tilde_D[t] >= Q_min * ON_DOWN[t_minus_one])
                model.add_constraint(tilde_D[t] <= q[t] - q[t_minus_one] - Q_min * (1 - ON_DOWN[t_minus_one]))
                model.add_constraint(
                    tilde_D[t] >= q[t] - q[t_minus_one] - Q_max * (1 - ON_DOWN[t_minus_one]),
                    "VALUE_of_tilde_DOWN_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Second stage : U and D
            # These variables wil be added to the gradient constraints.
            for t in time_frame:
                # U (eq. (27))
                model.add_constraint(U[t] <= Q_max * ON_UP[t])
                model.add_constraint(U[t] >= Q_min * ON_UP[t])
                model.add_constraint(U[t] <= tilde_U[t] - Q_min * (1 - ON_UP[t]))
                model.add_constraint(
                    U[t] >= tilde_U[t] - Q_max * (1 - ON_UP[t]),
                    "VALUE_of_UP_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )
                # D (eq. (29))
                model.add_constraint(D[t] <= Q_max * ON_DOWN[t])
                model.add_constraint(D[t] >= Q_min * ON_DOWN[t])
                model.add_constraint(D[t] <= tilde_D[t] - Q_min * (1 - ON_DOWN[t]))
                model.add_constraint(
                    D[t] >= tilde_D[t] - Q_max * (1 - ON_DOWN[t]),
                    "VALUE_of_DOWN_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # DD Gradient auxiliary (eq. (23))
            for t in gradients_time_frame:
                t_plus_one = t + parameters.time_step
                model.add_constraint(DD[t] <= Q_max * STOP[t_plus_one])
                model.add_constraint(DD[t] >= Q_min * STOP[t_plus_one])
                model.add_constraint(DD[t] <= D[t] - Q_min * (1 - STOP[t_plus_one]))
                model.add_constraint(
                    DD[t] >= D[t] - Q_max * (1 - STOP[t_plus_one]),
                    "DD_gradient_auxiliary_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in time_frame_union_minus_one:
                # Defined over the whole time frame.
                # Enforces eq. (9)
                model.add_constraint(
                    OFF[t] + ON_UP[t] + ON_DOWN[t] + ON_FLAT[t] + STOP[t] == 1,
                    "mutual_exclusion_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Transitions:
            # UP-DOWN and DOWN-UP transitions are forbidden.
            # STOP to ON transitions are also forbidden
            # OFF to STOP transitions
            # Finally, we forbid ON_UP to STOP (which never happens in practice) in order
            # to avoid defining a UU auxiliary analoguous to DD.
            for t in time_frame_union_minus_one:
                t_minus_one = t - parameters.time_step
                # Implement eq. (25)
                model.add_constraint(ON_UP[t_minus_one] + ON_DOWN[t] <= 1)
                model.add_constraint(ON_DOWN[t_minus_one] + ON_UP[t] <= 1)
                # Eq (13)
                model.add_constraint(STOP[t_minus_one] + ON_FLAT[t] <= 1)
                model.add_constraint(STOP[t_minus_one] + ON_DOWN[t] <= 1)
                model.add_constraint(
                    STOP[t_minus_one] + ON_UP[t] <= 1,
                    "transitions_constraints_on_timeFrame_union_minus_one_at_{}".format(
                        Utilities.get_date_to_clean_string(t)
                    ),
                )
            for t in time_frame:
                t_minus_one = t - parameters.time_step
                # ON_UP to STOP transition (eq. (21))
                model.add_constraint(ON_UP[t_minus_one] + STOP[t] <= 1)
                # Eq. (12)
                model.add_constraint(
                    OFF[t_minus_one] + STOP[t] <= 1,
                    "transitions_constraints_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )
                # The latter constraints are only defined on the time_frame because it does not involve ON variables at the t index.

            # Eviction constraint
            # The unit must leave the STOP state after T_stop time steps.
            for t in time_frame:
                t_minus_T_stop = t - T_stop * parameters.time_step
                # Implements equation (19)
                model.add_constraint(
                    turned_off[t_minus_T_stop] + STOP[t] <= 1,
                    "eviction_constraint_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

                # Mininum time on and minimum time off constraints:
            # if T_on >= 2 or T_off >= 2 or T_stable >= 2, lock the unit in this state.
            if T_on >= 2:
                for t in time_frame_union_minus_one:
                    time_steps = range(1, T_on)  # Corresponds to the set {1,..., T_on - 1}
                    for s in time_steps:
                        # Enforces eq. (31), with T_start = 0
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            turned_on[t_minus_s] <= ON_UP[t] + ON_DOWN[t] + ON_FLAT[t],
                            "minimum_time_ON_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_off >= 2:
                for t in time_frame:
                    time_steps = range(1, T_off)  # Corresponds to the set {1,..., T_off - 1}
                    for s in time_steps:
                        # Enforces eq. (32) with T_stop > 0
                        t_minus_s_minus_T_stop = t - s * parameters.time_step - T_stop * parameters.time_step
                        model.add_constraint(
                            turned_off[t_minus_s_minus_T_stop] <= OFF[t],
                            "minimum_time_OFF_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s_minus_T_stop),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_stable >= 2:
                for t in time_frame_union_minus_one:
                    time_steps = range(1, T_stable - 1)  # Corresponds to the set {1,..., T_stable - 1}
                    for s in time_steps:
                        # Enforces eq. (26)
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            stable[t_minus_s] <= ON_FLAT[t],
                            "minimum_time_STABLE_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_stop >= 2:
                for t in time_frame:
                    for s in stop_time_steps:
                        t_minus_s = t - s * parameters.time_step
                        # Enforces eq. (24)
                        model.add_constraint(
                            turned_off[t_minus_s] <= STOP[t],
                            "shutdown_ramp_of_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Start-up gradient:
            q_min = thermal_unit.minimum_power.max()
            q_step = q_min / T_stop

            # Reserves requirements
            # We are in a case where there is a FLAT state, so manual reserves can only be provided
            # when the unit is in the FLAT state.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))
            for t in time_frame:
                # contractedDifference
                model.add_constraint(contracted_difference_up[t] >= reserves_up_procured.get_value(t) - reserves_up[t])
                model.add_constraint(
                    contracted_difference_down[t] >= reserves_down_procured.get_value(t) - reserves_down[t]
                )
                # automatedContractedDifference
                model.add_constraint(
                    automated_contracted_difference_up[t]
                    >= feasible_automated_reserves_up_procured[t] - automated_reserves_up[t]
                )
                model.add_constraint(
                    automated_contracted_difference_down[t]
                    >= feasible_automated_reserves_down_procured[t] - automated_reserves_down[t]
                )

            # Upward and downward "fill up" constraints.
            for t in time_frame:
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    <= q_upper.get_value(t) + parameters.epsilon
                )  # Upward constraint - eq. (41)
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    >= q_upper.get_value(t) - parameters.epsilon
                )  # Upward constraint - eq. (41)

                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    <= q_lower.get_value(t) + parameters.epsilon
                )  # Downward constraint - eq. (42)
                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    >= q_lower.get_value(t) - parameters.epsilon
                )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            for t in time_frame:
                model.add_constraint(
                    relaxed_reserves[t] <= q_lower.get_value(t) * (1 - ON_UP[t] - ON_FLAT[t] - ON_DOWN[t])
                )

            # impossible commitment and stable reserves constraints (eqs. (44) and (45))
            for t in time_frame:
                model.add_constraint(automated_reserves_up[t] <= maximum_automated * (1 - OFF[t] - STOP[t]))
                model.add_constraint(automated_reserves_down[t] <= maximum_automated * (1 - OFF[t] - STOP[t]))
                model.add_constraint(
                    reserves_up[t] <= q_upper.get_value(t) * (1 - ON_UP[t] - ON_DOWN[t] - OFF[t] - STOP[t])
                )
                # for compacity, implements both eq (44) and (45)
                model.add_constraint(
                    reserves_down[t] <= q_upper.get_value(t) * (1 - ON_UP[t] - ON_DOWN[t] - OFF[t] - STOP[t])
                )

            # Power output
            for t in time_frame:
                model.add_constraint(
                    q[t]
                    >= q_lower.get_value(t) * (ON_UP[t] + ON_DOWN[t] + ON_FLAT[t]) + turned_off[t] * (q_min - q_step),
                    "lower_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Lower bound (eq. (33))

                model.add_constraint(
                    q[t]
                    <= q_upper.get_value(t) * (ON_UP[t] + ON_DOWN[t] + ON_FLAT[t])
                    + STOP[t] * q_min
                    - turned_off[t] * q_step,
                    "upper_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Upper bound (eq. (34))

            # Power gradients
            if delta_q > 0:  # Case where the gradient is finite.
                for t in gradients_time_frame:  # The gradients are defined only up to T-1.
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. (35))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= (
                            delta_q * entered_up[t]
                            + U[t]
                            + D[t]
                            - q_step * turned_off[t_next]
                            - STOP[t] * q_step
                            + delta_q_unconstrained * turned_on[t_next]
                            - DD[t]
                        ),
                        "upward_gradient_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (37))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= (
                            -delta_q * entered_down[t]
                            + U[t]
                            + D[t]
                            - q_step * turned_off[t_next]
                            - STOP[t] * q_step
                            + flat_down_stop[t_next] * delta_q
                            - DD[t]
                        ),
                        "downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient

            elif delta_q == 0:  # Case where the gradient is 'infinite'
                for t in gradients_time_frame:
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward unconstrained gradient (eq. (36))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= (
                            delta_q_unconstrained * entered_up[t]
                            + U[t]
                            + D[t]
                            - q_step * turned_off[t_next]
                            - STOP[t] * q_step
                            + delta_q_unconstrained * turned_on[t_next]
                        ),
                        "unconstrained_upward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (38))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= (
                            -delta_q_unconstrained * entered_down[t]
                            + U[t]
                            + D[t]
                            - q_step * turned_off[t_next]
                            - STOP[t] * q_step
                            + flat_down_stop[t_next] * delta_q_unconstrained
                            - DD[t]
                        ),
                        "unconstrained_downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient

            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    "*** WARNING ***\n No gradients have been defined for equipment {}. \n "
                    "Please check the value of `maximum_gradient`.".format(thermal_unit.name)
                )
                raise ValueError("Missing gradients for thermic units.")

                # Energy limits
            if thermal_unit.has_daily_energy_constraint:
                days_in_time_frame = []

                for local_time in time_frame:
                    if datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0) not in days_in_time_frame:
                        days_in_time_frame.append(datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0))

                for date in days_in_time_frame:
                    upper_bound = thermal_unit.maximum_daily_energy.get_value(date)

                    matching_steps = []
                    for local_time in time_frame:
                        if (
                            (local_time.year == date.year)
                            and (local_time.month == date.month)
                            and (local_time.day == date.day)
                        ):
                            matching_steps.append(local_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        model.add_constraint(
                            sum(q[t] for t in matching_steps)
                            <= upper_bound * parameters.time_step / 1440.0 * len(matching_steps),
                            "energy_limit_of_{}_at_{}".format(
                                thermal_unit.name, Utilities.get_date_to_clean_string(date)
                            ),
                        )
                        # TimeStep / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                              #
        ###   Combination 6 : T_stop =0, T_stable = T_start >= 1     ###
        #                                                              #
        # -------------------------------------------------------------#

        if T_stop == 0 and T_start >= 1 and T_stable >= 1:
            # In this case, there are five state variables and the following auxiliary variables :
            #     - turned_on[t] and turned_off[t], indicating whether the unit has been turned on or off
            #     - stable[t], indicating whether the unit entered the stable state
            #     - U[t] and D[t], implemented in two stages with tilde_D[t], tilde_D[t] as the first stage
            #     - entered_up[t] and entered_down[t] indicating that the unit entered the UP or down STATE
            #
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # A. INITIAL CONDITIONS

            # Define the startDate - 2 time steps.
            start_date_minus_two = parameters.start_date - 2 * parameters.time_step

            # Retrieve the values of the Power attribute over previous_time_frame
            last_power = thermal_unit.power.get_forecast(
                parameters.execution_date, extended_start_date, parameters.start_date - parameters.time_step
            )  # Extract the time series corresponding to the previous period
            last_date = last_power.last_date  # get the last date with a recorded value

            # See if the program needs to be initialized as DayZero or not
            if len(last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif last_date != parameters.start_date - parameters.time_step:
                # last_date doesn't match startDate - TimeStep (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                if parameters.verbose:
                    cfg.logger.warning(
                        "***WARNING***\n The last_date found in Power of equipement {} "
                        "does not match the startDate of the current program. \n "
                        "The program will be initialized as DayZero.".format(thermal_unit.name)
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if parameters.verbose:
                    cfg.logger.info(
                        "Initial conditions of unit {} have been set as in equation (47).".format(thermal_unit.name)
                    )

                for t in previous_time_frame:
                    # Initial conditions on the power output
                    q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    OFF[t] = 1
                    START[t] = 0
                    if not t == start_date_minus_one:
                        ON_UP[t] = 0
                        ON_DOWN[t] = 0
                        ON_FLAT[t] = 0
                        # Initial conditions on the auxiliary variables defined over time_frame_union_minus_one
                        stable[t] = 0
                        entered_up[t] = 0
                        entered_down[t] = 0

                    # Initial conditions on the remaining auxiliary variables
                    turned_on[t] = 0
                    turned_off[t] = 0
            else:
                # Setting up the initial conditions will be a bit more complex. We consecutively do the following:
                #    - Set the inital conditions on the power output
                #    - See wether the unit is ON, OFF or START
                #    - Initialize the auxiliaries turned_up and turned_down accordingly
                #    - For the steps where the unit is ON:
                #         - See whether the unit was UP, DOWN or FLAT
                #         - Initialize the auxiliary variables accordingly

                # Initial condition on the power output
                for t in previous_time_frame:
                    q[t] = last_power.get_value(t)

                # Initial conditions on the state variables.
                # The initialization is done in two times. If we are not at start_date_minus_one and not ON,
                # we initialize all the state variables, otherwise an additional loop will be done to
                # initialize the ON state variables from start_date_minus_two.
                for t in previous_time_frame:
                    if last_power.get_value(t) >= thermal_unit.minimum_power.get_value(t):
                        OFF[t] = 0
                        START[t] = 0
                    elif last_power.get_value(t) > 0:
                        OFF[t] = 0
                        START[t] = 1
                        if not t == start_date_minus_one:
                            ON_UP[t] = 0
                            ON_FLAT[t] = 0
                            ON_DOWN[t] = 0
                    else:
                        OFF[t] = 1
                        START[t] = 0
                        if not t == start_date_minus_one:
                            ON_UP[t] = 0
                            ON_DOWN[t] = 0
                            ON_FLAT[t] = 0

                # Reconstruct the values of UP, DOWN and FLAT state variables
                for t in previous_time_frame[
                    :-1
                ]:  # Loop excluding last date because we are reconstructing the values of the
                    # ON variables using  variations between q[t] and q[t-1].
                    t_prev = t - parameters.time_step
                    if q[t_prev] >= thermal_unit.minimum_power.get_value(t_prev):
                        # See if the power output was stable, increasing or decreasing:
                        if q[t] > q[t_prev]:  # Recall that here t_prev is earlier than t.
                            ON_UP[t_prev] = 1
                            ON_DOWN[t_prev] = 0
                            ON_FLAT[t_prev] = 0
                        elif q[t] < q[t_prev]:
                            ON_UP[t_prev] = 0
                            ON_DOWN[t_prev] = 1
                            ON_FLAT[t_prev] = 0
                        elif q[t] == q[t_prev]:
                            ON_UP[t_prev] = 0
                            ON_DOWN[t_prev] = 0
                            ON_FLAT[t_prev] = 1

                # Initial conditions on the auxiliary variables turned_on and turned_off.
                for t in previous_time_frame:
                    # Initialize all the values to 0
                    turned_on[t] = 0
                    turned_off[t] = 0
                    if not t == extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - parameters.time_step
                        # See if the unit has been turned off
                        if OFF[t] - OFF[t_prev] == 1:
                            turned_off[t] = 1
                        # Or turned on
                        elif START[t] - START[t_prev] == 1:
                            turned_on[t] = 1

                # Initialize the auxiliary variables entered_up, entered_down and stable.
                for t in previous_time_frame[
                    1:
                ]:  # Loop excluding start_date_minus_one, which is the first element in the previous_time_frame list.
                    # Default value set to 0
                    stable[t] = 0
                    entered_up[t] = 0
                    entered_down[t] = 0

                    if (not t == extended_start_date) and (not OFF[t] == 1):
                        t_prev = t - parameters.time_step

                        # See if the unit entered the FLAT state
                        if ON_FLAT[t] - ON_FLAT[t_prev] == 1:
                            stable[t] = 1
                        # or the UP state
                        if ON_UP[t] - ON_UP[t_prev] == 1:
                            entered_up[t] = 1
                        # or the DOWN state
                        if ON_DOWN[t] - ON_DOWN[t_prev] == 1:
                            entered_down[t] = 1

                            # Initialize the gradient auxiliaries. This is only required for the last time step of the
            # previous_time_frame. Only ON_UP[start_date_minus_one] and ON_DOWN[start_date_minus_one] are decision variables
            # in the expressions below.
            U[start_date_minus_one] = (
                ON_UP[start_date_minus_one]
                * ON_UP[start_date_minus_two]
                * (q[start_date_minus_one] - q[start_date_minus_two])
            )
            D[start_date_minus_one] = (
                ON_DOWN[start_date_minus_one]
                * ON_DOWN[start_date_minus_two]
                * (q[start_date_minus_one] - q[start_date_minus_two])
            )

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them : turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Enforces eq. (3)
            for t in time_frame:
                model.add_constraint(turned_on[t] <= 1 - OFF[t])
                model.add_constraint(turned_on[t] <= OFF[t - parameters.time_step])
                model.add_constraint(turned_on[t] >= OFF[t - parameters.time_step] - OFF[t])

                # Constraints on turned_off
            # Enforces eq. (4) as there is no STOP state in this case.
            for t in time_frame:
                model.add_constraint(turned_off[t] <= 1 - OFF[t - parameters.time_step])
                model.add_constraint(turned_off[t] <= OFF[t])
                model.add_constraint(turned_off[t] >= OFF[t] - OFF[t - parameters.time_step])

            # stable auxiliary variable
            # Enforces eq. (6)
            for t in time_frame_union_minus_one:
                model.add_constraint(stable[t] <= 1 - ON_FLAT[t - parameters.time_step])
                model.add_constraint(stable[t] <= ON_FLAT[t])
                model.add_constraint(stable[t] >= ON_FLAT[t] - ON_FLAT[t - parameters.time_step])

            # entered_up and entered_down auxiliaries
            for t in time_frame_union_minus_one:
                # entered_up (eq. (7))
                model.add_constraint(entered_up[t] <= 1 - ON_UP[t - parameters.time_step])
                model.add_constraint(entered_up[t] <= ON_UP[t])
                model.add_constraint(entered_up[t] >= ON_UP[t] - ON_UP[t - parameters.time_step])
                # entered_down (eq. (8))
                model.add_constraint(entered_down[t] <= 1 - ON_DOWN[t - parameters.time_step])
                model.add_constraint(entered_down[t] <= ON_DOWN[t])
                model.add_constraint(entered_down[t] >= ON_DOWN[t] - ON_DOWN[t - parameters.time_step])

            # UP and DOWN auxiliary variables for the gradient.
            # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
            # power output twice in a row, then the second time the gradient is locked.
            # In practice, these variables are defined in two stages

            # First stage : tilde_U and tilde_D
            for t in time_frame:  # Loop in all the time_frame but startDate.
                t_minus_one = t - parameters.time_step
                # tilde_U (eq. (28))
                model.add_constraint(tilde_U[t] <= Q_max * ON_UP[t_minus_one])
                model.add_constraint(tilde_U[t] >= Q_min * ON_UP[t_minus_one])
                model.add_constraint(tilde_U[t] <= q[t] - q[t_minus_one] - Q_min * (1 - ON_UP[t_minus_one]))
                model.add_constraint(
                    tilde_U[t] >= q[t] - q[t_minus_one] - Q_max * (1 - ON_UP[t_minus_one]),
                    "VALUE_of_tilde_UP_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

                # tilde_D (eq. (30))
                model.add_constraint(tilde_D[t] <= Q_max * ON_DOWN[t_minus_one])
                model.add_constraint(tilde_D[t] >= Q_min * ON_DOWN[t_minus_one])
                model.add_constraint(tilde_D[t] <= q[t] - q[t_minus_one] - Q_min * (1 - ON_DOWN[t_minus_one]))
                model.add_constraint(
                    tilde_D[t] >= q[t] - q[t_minus_one] - Q_max * (1 - ON_DOWN[t_minus_one]),
                    "VALUE_of_tilde_DOWN_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Second stage : U and D
            # These variables wil be added to the gradient constraints.
            for t in time_frame:
                # U (eq. (27))
                model.add_constraint(U[t] <= Q_max * ON_UP[t])
                model.add_constraint(U[t] >= Q_min * ON_UP[t])
                model.add_constraint(U[t] <= tilde_U[t] - Q_min * (1 - ON_UP[t]))
                model.add_constraint(
                    U[t] >= tilde_U[t] - Q_max * (1 - ON_UP[t]),
                    "VALUE_of_UP_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )
                # D (eq. (29))
                model.add_constraint(D[t] <= Q_max * ON_DOWN[t])
                model.add_constraint(D[t] >= Q_min * ON_DOWN[t])
                model.add_constraint(D[t] <= tilde_D[t] - Q_min * (1 - ON_DOWN[t]))
                model.add_constraint(
                    D[t] >= tilde_D[t] - Q_max * (1 - ON_DOWN[t]),
                    "VALUE_of_DOWN_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in time_frame_union_minus_one:
                # Defined over the whole time frame.
                # Enforces eq. (9)
                model.add_constraint(
                    OFF[t] + ON_UP[t] + ON_DOWN[t] + ON_FLAT[t] + START[t] == 1,
                    "mutual_exclusion_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Transitions:
            # UP-DOWN and DOWN-UP transitions are forbidden.
            for t in time_frame_union_minus_one:
                t_minus_one = t - parameters.time_step
                # Implement eq. (25).
                model.add_constraint(ON_UP[t_minus_one] + ON_DOWN[t] <= 1)
                model.add_constraint(ON_DOWN[t_minus_one] + ON_UP[t] <= 1)

            # Constraints involving START and OFF are only defined on the time_frame time frame.
            for t in time_frame:
                t_minus_one = t - parameters.time_step
                # Eq. (10)
                model.add_constraint(ON_UP[t_minus_one] + START[t] <= 1)
                model.add_constraint(ON_DOWN[t_minus_one] + START[t] <= 1)
                model.add_constraint(ON_FLAT[t_minus_one] + START[t] <= 1)
                # Eq. (11)
                model.add_constraint(START[t_minus_one] + OFF[t] <= 1)
                # Eq. (15)
                model.add_constraint(OFF[t_minus_one] + ON_UP[t] <= 1)
                model.add_constraint(OFF[t_minus_one] + ON_DOWN[t] <= 1)
                model.add_constraint(
                    OFF[t_minus_one] + ON_FLAT[t] <= 1,
                    "transitions_constraints_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Eviction constraint
            # The unit must leave the START state after T_start time steps.
            for t in time_frame:
                t_minus_T_start = t - T_start * parameters.time_step
                # Implement equation (16)
                model.add_constraint(
                    turned_on[t_minus_T_start] + START[t] <= 1,
                    "eviction_constraint_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Mininum time on and minimum time off constraints:
            # if T_on >= 2 or T_off >= 2 or T_stable >= 2, lock the unit in this state.
            if T_on >= 2:
                for t in time_frame_union_minus_one:
                    time_steps = range(1, T_on)  # Corresponds to the set {1,..., T_on - 1}
                    for s in time_steps:
                        # Enforces eq. (31), with T_start > 0
                        t_minus_s_minus_T_start = t - s * parameters.time_step - T_start * parameters.time_step
                        model.add_constraint(
                            turned_on[t_minus_s_minus_T_start] <= ON_UP[t] + ON_DOWN[t] + ON_FLAT[t],
                            "minimum_time_ON_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s_minus_T_start),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_off >= 2:
                for t in time_frame:
                    time_steps = range(1, T_off)  # Corresponds to the set {1,..., T_off - 1}
                    for s in time_steps:
                        # Enforces eq. (32) with T_stop = 0
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            turned_off[t_minus_s] <= OFF[t],
                            "minimum_time_OFF_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_stable >= 2:
                for t in time_frame_union_minus_one:
                    time_steps = range(1, T_stable - 1)  # Corresponds to the set {1,..., T_stable - 2}
                    for s in time_steps:
                        # Enforces eq. (26)
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            stable[t_minus_s] <= ON_FLAT[t],
                            "minimum_time_STABLE_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_start >= 2:
                for t in time_frame:
                    for s in start_time_steps:
                        t_minus_s = t - s * parameters.time_step
                        # Enforces eq. (17)
                        model.add_constraint(
                            turned_on[t_minus_s] <= START[t],
                            "start_up_ramp_of_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Start-up gradient:
            q_min = thermal_unit.minimum_power.max()
            q_step = q_min / T_start

            # Reserves requirements
            # We are in a case where there is a FLAT state, so manual reserves can only be provided
            # when the unit is in the FLAT state.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))
            for t in time_frame:
                # contractedDifference
                model.add_constraint(contracted_difference_up[t] >= reserves_up_procured.get_value(t) - reserves_up[t])
                model.add_constraint(
                    contracted_difference_down[t] >= reserves_down_procured.get_value(t) - reserves_down[t]
                )
                # automatedContractedDifference
                model.add_constraint(
                    automated_contracted_difference_up[t]
                    >= feasible_automated_reserves_up_procured[t] - automated_reserves_up[t]
                )
                model.add_constraint(
                    automated_contracted_difference_down[t]
                    >= feasible_automated_reserves_down_procured[t] - automated_reserves_down[t]
                )

            # Upward and downward "fill up" constraints.
            for t in time_frame:
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    <= q_upper.get_value(t) + parameters.epsilon
                )  # Upward constraint - eq. (41)
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    >= q_upper.get_value(t) - parameters.epsilon
                )  # Upward constraint - eq. (41)

                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    <= q_lower.get_value(t) + parameters.epsilon
                )  # Downward constraint - eq. (42)
                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    >= q_lower.get_value(t) - parameters.epsilon
                )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            for t in time_frame:
                model.add_constraint(
                    relaxed_reserves[t] <= q_lower.get_value(t) * (1 - ON_UP[t] - ON_FLAT[t] - ON_DOWN[t])
                )

            # impossible commitment and stable reserves constraints (eqs. (44) and (45))
            for t in time_frame:
                model.add_constraint(automated_reserves_up[t] <= maximum_automated * (1 - OFF[t] - START[t]))
                model.add_constraint(automated_reserves_down[t] <= maximum_automated * (1 - OFF[t] - START[t]))
                model.add_constraint(
                    reserves_up[t] <= q_upper.get_value(t) * (1 - ON_UP[t] - ON_DOWN[t] - OFF[t] - START[t])
                )
                # for compacity, implements both eq (44) and (45)
                model.add_constraint(
                    reserves_down[t] <= q_upper.get_value(t) * (1 - ON_UP[t] - ON_DOWN[t] - OFF[t] - START[t])
                )

            # Power output
            for t in time_frame:
                model.add_constraint(
                    q[t] >= q_lower.get_value(t) * (ON_UP[t] + ON_DOWN[t] + ON_FLAT[t]),
                    "lower_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Lower bound (eq. (33))
                model.add_constraint(
                    q[t] <= q_upper.get_value(t) * (ON_UP[t] + ON_DOWN[t] + ON_FLAT[t]) + START[t] * q_min,
                    "upper_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Upper bound (eq. (34))

            # Power gradients
            # Definition of the gradients_time_frame : starts at startDate - TimeStep and goes until T-1
            # Gradients are defined on a "shifted" time frame.
            gradients_time_frame = generate_datetimes(
                parameters.start_date - parameters.time_step,
                parameters.end_optimization_date - 2 * parameters.time_step,
                parameters.time_step,
            )

            if delta_q > 0:  # Case where the gradient is finite.
                for t in gradients_time_frame:  # The gradients are defined only up to T-1.
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. (35))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= delta_q * entered_up[t] + U[t] + D[t] + q_step * turned_on[t_next] + START[t] * q_step,
                        "upward_gradient_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                    )  # Upward gradient

                    # Downard constrained gradient (eq. (37))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= (
                            -delta_q * entered_down[t]
                            + U[t]
                            + D[t]
                            - delta_q_unconstrained * turned_off[t_next]
                            + q_step * turned_on[t_next]
                            + START[t] * q_step
                        ),
                        "downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient

            elif delta_q == 0:  # Case where the gradient is 'infinite'
                for t in gradients_time_frame:
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward unconstrained gradient (eq. (36))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= delta_q_unconstrained * entered_up[t]
                        + U[t]
                        + D[t]
                        + q_step * turned_on[t_next]
                        + START[t] * q_step,
                        "unconstrained_upward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (38))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= (
                            -delta_q_unconstrained * entered_down[t]
                            + U[t]
                            + D[t]
                            - delta_q_unconstrained * turned_off[t_next]
                            + q_step * turned_on[t_next]
                            + START[t] * q_step
                        ),
                        "unconstrained_downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient

            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    "*** WARNING ***\n No gradients have been defined for equipment {}. \n "
                    "Please check the value of `maximum_gradient`.".format(thermal_unit.name)
                )
                raise ValueError("Missing gradients for thermic units.")

                # Energy limits
            if thermal_unit.has_daily_energy_constraint:
                days_in_time_frame = []

                for local_time in time_frame:
                    if datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0) not in days_in_time_frame:
                        days_in_time_frame.append(datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0))

                for date in days_in_time_frame:
                    upper_bound = thermal_unit.maximum_daily_energy.get_value(date)

                    matching_steps = []
                    for local_time in time_frame:
                        if (
                            (local_time.year == date.year)
                            and (local_time.month == date.month)
                            and (local_time.day == date.day)
                        ):
                            matching_steps.append(local_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        model.add_constraint(
                            sum(q[t] for t in matching_steps)
                            <= upper_bound * parameters.time_step / 1440.0 * len(matching_steps),
                            "energy_limit_of_{}_at_{}".format(
                                thermal_unit.name, Utilities.get_date_to_clean_string(date)
                            ),
                        )
                        # TimeStep / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                              #
        ### Combination 7 : T_stop >= 1, T_stable = 0 T_start >= 1   ###
        #                                                              #
        # -------------------------------------------------------------#

        if T_stop >= 1 and T_start >= 1 and T_stable == 0:
            # In this case, there are five state variables and two auxiliary variables.
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # PREAMBLE
            # Define the down_to_stop auxiliary, which is used in this combination and in combination 2
            down_to_stop = {}
            for t in time_frame:
                down_to_stop[t] = model.add_continuous_variable(
                    "down_to_stop_equip_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)), 0, 1
                )

            # A. INITIAL CONDITIONS

            # Retrieve the values of the Power attribute over previous_time_frame
            last_power = thermal_unit.power.get_forecast(
                parameters.execution_date, extended_start_date, parameters.start_date - parameters.time_step
            )  # Extract the time series corresponding to the previous period

            last_date = last_power.last_date  # get the last date with a recorded value

            # See if the program needs to be initialized as DayZero or not
            if len(last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif last_date != parameters.start_date - parameters.time_step:
                # last_date doesn't match startDate - TimeStep (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                if parameters.verbose:
                    cfg.logger.warning(
                        "***WARNING***\n The last_date found in Power of equipement {} "
                        "does not match the startDate of the current program. \n "
                        "The program will be initialized as DayZero.".format(thermal_unit.name)
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if parameters.verbose:
                    cfg.logger.info(
                        "Initial conditions of unit {} have been set as in equation (47).".format(thermal_unit.name)
                    )

                for t in previous_time_frame:
                    # Initial conditions on the power output
                    q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    OFF[t] = 1
                    ON_UP[t] = 0
                    ON_DOWN[t] = 0
                    STOP[t] = 0
                    START[t] = 0
                    # Initial conditions on the auxiliary variables
                    turned_on[t] = 0
                    turned_off[t] = 0
                    down_to_stop[t] = 0
            else:
                # Initial condition on the power output
                for t in previous_time_frame:
                    q[t] = last_power.get_value(t)

                # Initial conditions on the state variables
                for t in previous_time_frame:
                    # There are now three cases : either q_t >= q_min, 0 < q_t < q_min or q_t = 0
                    if last_power.get_value(t) >= thermal_unit.minimum_power.get_value(t):
                        OFF[t] = 0
                        STOP[t] = 0
                        START[t] = 0
                        ON_DOWN[t] = 1
                        ON_UP[t] = (
                            1  # Set both ON states to 1 in order to allow the unit to do whatever it wants as there is no
                        )
                        # stable constraint at this point.
                    elif (
                        last_power.get_value(t) > 0
                    ):  # We will below see whether the unit was being turned on or turned off.
                        STOP[t] = 1
                        START[t] = 1
                        OFF[t] = 0
                        ON_UP[t] = 0
                        ON_DOWN[t] = 0
                    else:
                        STOP[t] = 0
                        START[t] = 0
                        OFF[t] = 1
                        ON_UP[t] = 0
                        ON_DOWN[t] = 0

                # Distinguish between start-ups and shutdowns
                # discard the extended_start_date only.
                for t in previous_time_frame[:-1]:
                    t_prev = t - parameters.time_step
                    if START[t] == 1:  # Take start or stop, does not matter.
                        if q[t] > q[t_prev]:  # If the power output increases, then we are starting up.
                            STOP[t] = 0
                            START[t] = 1
                        elif q[t] < q[t_prev]:  # otherwise we are shutting down the unit.
                            STOP[t] = 1
                            START[t] = 0

                            # Initial conditions on the auxiliary variables
                for t in previous_time_frame:
                    # Initialize all the values to 0
                    turned_on[t] = 0
                    turned_off[t] = 0
                    down_to_stop[t] = 0
                    if not t == extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - parameters.time_step
                        # See if the unit has been turned off
                        if STOP[t] - STOP[t_prev] == 1:
                            turned_off[t] = 1
                        # Or turned on
                        elif START[t] - START[t_prev] == 1:
                            turned_on[t] = 1
                        # Reconstruction of down_to_stop
                        elif STOP[t] - ON_DOWN[t_prev] == 0:
                            down_to_stop[t] = 1

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them : turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Amounts to leaving the OFF state, due to the mutual exclusion and transition constraints.
            # Enforces eq (3).
            for t in time_frame:
                model.add_constraint(turned_on[t] <= 1 - OFF[t])
                model.add_constraint(turned_on[t] <= OFF[t - parameters.time_step])
                model.add_constraint(
                    turned_on[t] >= OFF[t - parameters.time_step] - OFF[t],
                    "constraints_defining_turned_on_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Constraints on turned_off
            # Defined here when entering the STOP state as in eq. (5) because T_stop > 0
            for t in time_frame:
                model.add_constraint(turned_off[t] <= 1 - STOP[t - parameters.time_step])
                model.add_constraint(turned_off[t] <= STOP[t])
                model.add_constraint(
                    turned_off[t] >= STOP[t] - STOP[t - parameters.time_step],
                    "constraints_defining_turned_off_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Constraints on down_to_stop (eq. (20))
            for t in time_frame:
                t_minus_one = t - parameters.time_step
                model.add_constraint(down_to_stop[t] <= STOP[t])
                model.add_constraint(down_to_stop[t] <= ON_DOWN[t_minus_one])
                model.add_constraint(down_to_stop[t] >= STOP[t] + ON_DOWN[t_minus_one] - 1)

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in time_frame:
                # Defined over the whole time frame
                # Enforces eq. (9)
                model.add_constraint(
                    OFF[t] + ON_UP[t] + ON_DOWN[t] + STOP[t] + START[t] == 1,
                    "mutual_exclusion_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Transitions:
            # Transitions from OFF to STOP and STOP to ON_DOWN and ON_UP are forbidden
            # Direct transitions from ON_UP and ON_DOWN to OFF are forbidden.
            # Transitions from ON_UP and ON_DOWN to START and START to OFF are forbidden
            # Direct transitions from OFF to ON_UP and ON_DOWN are forbidden.
            for t in time_frame:
                t_minus_one = t - parameters.time_step
                # STOP to ON (eq. (13))
                model.add_constraint(STOP[t_minus_one] + ON_UP[t] <= 1)
                model.add_constraint(STOP[t_minus_one] + ON_DOWN[t] <= 1)
                # OFF to STOP (eq. (12))
                model.add_constraint(OFF[t_minus_one] + STOP[t] <= 1)
                # ON to OFF (eq.(18) )
                model.add_constraint(ON_UP[t_minus_one] + OFF[t] <= 1)
                model.add_constraint(ON_DOWN[t_minus_one] + OFF[t] <= 1)
                # ON to START (eq. (10))
                model.add_constraint(ON_UP[t_minus_one] + START[t] <= 1)
                model.add_constraint(ON_DOWN[t_minus_one] + START[t] <= 1)
                # START to OFF (eq. (11))
                model.add_constraint(START[t_minus_one] + OFF[t] <= 1)
                # START to STOP and STOP to START (eq. (14))
                model.add_constraint(START[t_minus_one] + STOP[t] <= 1)
                model.add_constraint(STOP[t_minus_one] + START[t] <= 1)
                # OFF to ON (eq. (15))
                model.add_constraint(OFF[t_minus_one] + ON_UP[t] <= 1)
                model.add_constraint(
                    OFF[t_minus_one] + ON_DOWN[t] <= 1,
                    "transitions_constraints_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

                # Eviction constraints.
            for t in time_frame:
                # Define t - T_start and t - T_stop.
                t_minus_T_start = t - T_start * parameters.time_step
                t_minus_T_stop = t - T_stop * parameters.time_step
                # Add the constraints.
                # Implements equation (16)
                model.add_constraint(
                    turned_on[t_minus_T_start] + START[t] <= 1,
                    "START_eviction_constraint_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )
                # Implements equation (19)
                model.add_constraint(
                    turned_off[t_minus_T_stop] + STOP[t] <= 1,
                    "STOP_eviction_constraint_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Mininum time on and minimum time off constraints:
            # if T_on >= 2, T_off >= 2 or T_stop >= 2, lock the unit in this state.
            if T_on >= 2:
                for t in time_frame:
                    time_steps = range(1, T_on)
                    for s in time_steps:
                        # Enforces eq. (31) with T_start > 0
                        t_minus_s_minus_T_start = t - s * parameters.time_step - T_start * parameters.time_step
                        model.add_constraint(
                            turned_on[t_minus_s_minus_T_start] <= ON_UP[t] + ON_DOWN[t],
                            "minimum_time_ON_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s_minus_T_start),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_off >= 2:
                for t in time_frame:
                    time_steps = range(1, T_off)
                    for s in time_steps:
                        # Enforces eq. (32) with T_stop > 0
                        # Shift the index because the OFF is formally considered when entering the STOP state.
                        t_minus_s_minus_T_stop = t - s * parameters.time_step - T_stop * parameters.time_step
                        model.add_constraint(
                            turned_off[t_minus_s_minus_T_stop] <= OFF[t],
                            "minimum_time_OFF_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s_minus_T_stop),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_stop >= 2:
                for t in time_frame:
                    for s in stop_time_steps:
                        # Enforces eq. (24)
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            turned_off[t_minus_s] <= STOP[t],
                            "shutdown_ramp_of_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_start >= 2:
                for t in time_frame:
                    for s in start_time_steps:
                        # Enforces eq. (17)
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            turned_on[t_minus_s] <= START[t],
                            "start_up_ramp_of_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Shutdown and start_up gradients
            q_min = thermal_unit.minimum_power.max()  # Get the minimumPower without the reserve requirements
            q_step_up = q_min / T_start
            q_step_down = q_min / T_stop

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))
            for t in time_frame:
                # contractedDifference
                model.add_constraint(contracted_difference_up[t] >= reserves_up_procured.get_value(t) - reserves_up[t])
                model.add_constraint(
                    contracted_difference_down[t] >= reserves_down_procured.get_value(t) - reserves_down[t]
                )
                # automatedContractedDifference
                model.add_constraint(
                    automated_contracted_difference_up[t]
                    >= feasible_automated_reserves_up_procured[t] - automated_reserves_up[t]
                )
                model.add_constraint(
                    automated_contracted_difference_down[t]
                    >= feasible_automated_reserves_down_procured[t] - automated_reserves_down[t]
                )

            # Upward and downward "fill up" constraints.
            for t in time_frame:
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    <= q_upper.get_value(t) + parameters.epsilon
                )  # Upward constraint - eq. (41)
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    >= q_upper.get_value(t) - parameters.epsilon
                )  # Upward constraint - eq. (41)

                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    <= q_lower.get_value(t) + parameters.epsilon
                )  # Downward constraint - eq. (42)
                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    >= q_lower.get_value(t) - parameters.epsilon
                )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            for t in time_frame:
                model.add_constraint(relaxed_reserves[t] <= q_lower.get_value(t) * (1 - ON_UP[t] - ON_DOWN[t]))

            # impossible commitment and stable reserves constraints (eq. (44))
            for t in time_frame:
                model.add_constraint(automated_reserves_up[t] <= maximum_automated * (1 - OFF[t] - START[t] - STOP[t]))
                model.add_constraint(
                    automated_reserves_down[t] <= maximum_automated * (1 - OFF[t] - START[t] - STOP[t])
                )
                model.add_constraint(reserves_up[t] <= q_upper.get_value(t) * (1 - OFF[t] - START[t] - STOP[t]))
                model.add_constraint(reserves_down[t] <= q_upper.get_value(t) * (1 - OFF[t] - START[t] - STOP[t]))

            # Power output
            for t in time_frame:
                model.add_constraint(
                    q[t] >= q_lower.get_value(t) * (ON_UP[t] + ON_DOWN[t]) + turned_off[t] * (q_min - q_step_down),
                    "lower_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )
                # Lower bound (eq. (33))
                model.add_constraint(
                    q[t]
                    <= q_upper.get_value(t) * (ON_UP[t] + ON_DOWN[t])
                    + STOP[t] * q_min
                    + START[t] * q_min
                    - turned_off[t] * q_step_down,
                    "upper_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )
                # Upper bound (eq. (34))

            # Power gradients
            # Definition of the gradients_time_frame : starts at startDate - TimeStep and goes until T-1
            gradients_time_frame = generate_datetimes(
                parameters.start_date - parameters.time_step,
                parameters.end_optimization_date - 2 * parameters.time_step,
                parameters.time_step,
            )

            if delta_q > 0:  # Case where the gradient is finite.
                for t in gradients_time_frame:  # The gradients are defined only up to T-1.
                    # NB. The downward gradient implemented here requires the unit to be at most at deltaQ in order to be able to enter the stop state.
                    # The resulting constraint set is considerably more constraining than if the gradient was relaxed.
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. (35))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= (
                            delta_q * ON_UP[t]
                            - turned_off[t_next] * q_step_down
                            - STOP[t] * q_step_down
                            + turned_on[t_next] * q_step_up
                            + START[t] * q_step_up
                        ),
                        "upward_gradient_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (37))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= (
                            -delta_q * ON_DOWN[t]
                            - turned_off[t_next] * q_step_down
                            - STOP[t] * q_step_down
                            + down_to_stop[t_next] * delta_q
                            + turned_on[t_next] * q_step_up
                            + START[t] * q_step_up
                        ),
                        "downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient
            elif delta_q == 0:
                for t in gradients_time_frame:
                    t_next = t + parameters.time_step

                    # Upward unconstrained gradient (eq. (36))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= (
                            delta_q_unconstrained * ON_UP[t]
                            - turned_off[t_next] * q_step_down
                            - STOP[t] * q_step_down
                            + turned_on[t_next] * q_step_up
                            + START[t] * q_step_up
                        ),
                        "unconstrained_upward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (38))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= (
                            -delta_q_unconstrained * ON_DOWN[t]
                            - turned_off[t_next] * q_step_down
                            - STOP[t] * q_step_down
                            + down_to_stop[t_next] * delta_q_unconstrained
                            + turned_on[t_next] * q_step_up
                            + START[t] * q_step_up
                        ),
                        "unconstrained_downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient
            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    "*** WARNING ***\n No gradients have been defined for equipment {}. \n "
                    "Please check the value of `maximum_gradient`.".format(thermal_unit.name)
                )
                raise ValueError("Missing gradients for thermic units.")

                # Energy limits
            if thermal_unit.has_daily_energy_constraint:
                days_in_time_frame = []

                for local_time in time_frame:
                    if datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0) not in days_in_time_frame:
                        days_in_time_frame.append(datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0))

                for date in days_in_time_frame:
                    upper_bound = thermal_unit.maximum_daily_energy.get_value(date)

                    matching_steps = []
                    for local_time in time_frame:
                        if (
                            (local_time.year == date.year)
                            and (local_time.month == date.month)
                            and (local_time.day == date.day)
                        ):
                            matching_steps.append(local_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        model.add_constraint(
                            sum(q[t] for t in matching_steps)
                            <= upper_bound * parameters.time_step / 1440.0 * len(matching_steps),
                            "energy_limit_of_{}_at_{}".format(
                                thermal_unit.name, Utilities.get_date_to_clean_string(date)
                            ),
                        )
                        # TimeStep / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                              #
        ####   Combination 8 : T_start = T_stable = T_stop >= 1     ####
        #                                                              #
        # -------------------------------------------------------------#

        if T_stop >= 1 and T_start >= 1 and T_stable >= 1:
            # In this case, there are six state variables and the following auxiliary variables :
            #     - turned_on[t] and turned_off[t], indicating whether the unit has been turned on or off
            #     - stable[t], indicating whether the unit entered the stable state
            #     - U[t] and D[t], implemented in two stages with tilde_D[t], tilde_D[t] as the first stage
            #     - entered_up[t] and entered_down[t] indicating that the unit entered the UP or down STATE
            #
            # We also need the gradient auxiliaries DD[t] and flat_down_stop[t] to follow the shut down procedure of
            # the unit.
            #
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # PREAMBLE
            # Definition of two additional auxiliary variables needed specifically to handle this case,
            # flat_down_stop, which detects when the unit follows a FLAT(t-2) - DOWN(t-1) and STOP(t) path
            # and DD, which detects if the unit is to be stopped at t+1 (i.e. STOP(t+1) = 1) after having been
            # in the DOWN state at time steps t and t-1.

            # flat_down_stop
            flat_down_stop = {}
            for t in time_frame:
                flat_down_stop[t] = model.add_continuous_variable(
                    "flat_down_stop_at_{}_equip_{}".format(Utilities.get_date_to_clean_string(t), thermal_unit.name),
                    0,
                    1,
                )

            # DD
            # Definition of the gradients_time_frame : starts at startDate - TimeStep and goes until T-1
            # Gradients are defined on a "shifted" time frame.
            gradients_time_frame = generate_datetimes(
                parameters.start_date - parameters.time_step,
                parameters.end_optimization_date - 2 * parameters.time_step,
                parameters.time_step,
            )

            DD = {}
            for t in gradients_time_frame:
                DD[t] = model.add_continuous_variable(
                    "DD_{}_equip_{}".format(Utilities.get_date_to_clean_string(t), thermal_unit.name), Q_min, Q_max
                )

            # A. INITIAL CONDITIONS

            # Define the startDate - 2 time steps.
            start_date_minus_two = parameters.start_date - 2 * parameters.time_step

            # Retrieve the values of the Power attribute over previous_time_frame
            last_power = thermal_unit.power.get_forecast(
                parameters.execution_date, extended_start_date, parameters.start_date - parameters.time_step
            )  # Extract the time series corresponding to the previous period

            last_date = last_power.last_date  # get the last date with a recorded value

            # See if the program needs to be initialized as DayZero or not
            if len(last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif last_date != parameters.start_date - parameters.time_step:
                # last_date doesn't match startDate - TimeStep (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                cfg.logger.warning(
                    "***WARNING***\n The last_date found in Power of equipement {} "
                    "does not match the startDate of the current program. \n "
                    "The program will be initialized as DayZero.".format(thermal_unit.name)
                )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                cfg.logger.info(
                    "Initial conditions of unit {} have been set as in equation (47).".format(thermal_unit.name)
                )

                for t in previous_time_frame:
                    # Initial conditions on the power output
                    q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    OFF[t] = 1
                    STOP[t] = 0
                    START[t] = 0
                    if not t == start_date_minus_one:
                        ON_UP[t] = 0
                        ON_DOWN[t] = 0
                        ON_FLAT[t] = 0
                        # Initial conditions on the auxiliary variables defined over time_frame_union_minus_one
                        stable[t] = 0
                        entered_up[t] = 0
                        entered_down[t] = 0

                    # Initial conditions on the remaining auxiliary variables
                    turned_on[t] = 0
                    turned_off[t] = 0
                    flat_down_stop[t] = 0
            else:
                # Setting up the initial conditions will be a bit more complex. We consecutively do the following:
                #    - Set the inital conditions on the power output
                #    - See wether the unit is ON or OFF
                #    - Initialize the auxiliaries turned_up and turned_down accordingly
                #    - For the steps where the unit is ON:
                #         - See whether the unit was UP, DOWN or FLAT
                #         - Initialize the auxiliary variables accordingly

                # Initial condition on the power output
                for t in previous_time_frame:
                    q[t] = last_power.get_value(t)

                # Initial conditions on the state variables OFF/ON
                for t in previous_time_frame:
                    if last_power.get_value(t) >= thermal_unit.minimum_power.get_value(t):
                        OFF[t] = (
                            0  # Only the OFF and STOP variables are initialized. ON_FLAT, ON_DOWN and ON_UP will be
                        )
                        # initialized afterwards.
                        STOP[t] = 0
                        START[t] = 0
                    elif last_power.get_value(t) > 0:
                        OFF[t] = 0
                        STOP[t] = 1  # Set both START and STOP at 1 for now, will be distinguished afterwards.
                        START[t] = 1
                        if not t == start_date_minus_one:
                            ON_UP[t] = 0
                            ON_DOWN[t] = 0
                            ON_FLAT[t] = 0
                    else:
                        OFF[t] = 1
                        STOP[t] = 0
                        START[t] = 0
                        if not t == start_date_minus_one:
                            ON_UP[t] = 0
                            ON_DOWN[t] = 0
                            ON_FLAT[t] = 0

                            # Distinguish between start-ups and shutdowns
                # discard the extended_start_date only.
                for t in previous_time_frame[:-1]:
                    t_prev = t - parameters.time_step
                    if START[t] == 1:  # Take start or stop, does not matter.
                        if q[t] > q[t_prev]:  # If the power output increases, then we are starting up.
                            STOP[t] = 0
                            START[t] = 1
                        elif q[t] < q[t_prev]:  # otherwise we are shutting down the unit.
                            STOP[t] = 1
                            START[t] = 0

                            # Initial conditions on the auxiliary variables turned_on turned_off
                for t in previous_time_frame:
                    # Initialize all the values to 0
                    turned_on[t] = 0
                    turned_off[t] = 0
                    if not t == extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - parameters.time_step
                        # See if the unit has been turned off
                        if STOP[t] - STOP[t_prev] == 1:
                            turned_off[t] = 1
                        # Or turned on
                        elif START[t] - START[t_prev] == 1:
                            turned_on[t] = 1

                # Reconstruct the values of UP, DOWN and FLAT and their associated
                # auxiliary variables
                for t in previous_time_frame[
                    :-1
                ]:  # Loop excluding last date because we are reconstructing the values of the
                    # ON variables using  variations between q[t] and q[t-1].

                    t_prev = t - parameters.time_step
                    if OFF[t_prev] == 0:
                        # See if the power output was stable, increasing or decreasing:
                        if q[t] > q[t_prev]:  # Recall that here t_prev is earlier than t.
                            ON_UP[t_prev] = 1
                            ON_DOWN[t_prev] = 0
                            ON_FLAT[t_prev] = 0
                        elif q[t] < q[t_prev]:
                            ON_UP[t_prev] = 0
                            ON_DOWN[t_prev] = 1
                            ON_FLAT[t_prev] = 0
                        elif q[t] == q[t_prev]:
                            ON_UP[t_prev] = 0
                            ON_DOWN[t_prev] = 0
                            ON_FLAT[t_prev] = 1

                # Initialize the auxiliary variables
                for t in previous_time_frame[
                    1:
                ]:  # Loop excluding start_date_minus_one, which is the first element in the previous_time_frame list.
                    # Default value set to 0
                    stable[t] = 0
                    entered_up[t] = 0
                    entered_down[t] = 0

                    if (not t == extended_start_date) and (not OFF[t] == 1):
                        t_prev = t - parameters.time_step

                        # See if the unit entered the FLAT state
                        if ON_FLAT[t] - ON_FLAT[t_prev] == 1:
                            stable[t] = 1
                        # or the UP state
                        if ON_UP[t] - ON_UP[t_prev] == 1:
                            entered_up[t] = 1
                        # or the DOWN state
                        if ON_DOWN[t] - ON_DOWN[t_prev] == 1:
                            entered_down[t] = 1

                # Initialize flat_down_stop.
                for t in previous_time_frame[:-2]:
                    # Moreover, if we are after extended_start_date + TimeStep
                    # initialize flat_down_stop (which traces back up to two time index before)
                    t_minus_one = t - parameters.time_step
                    t_minus_two = t - 2 * parameters.time_step
                    flat_down_stop[t] = int(math.floor((STOP[t] + ON_DOWN[t_minus_one] + ON_FLAT[t_minus_two]) / 3))

                    # Initialize the gradient auxiliaries. This is only required for the last time step of the
            # previous_time_frame. Only ON_UP[start_date_minus_one] and ON_DOWN[start_date_minus_one] are decision variables
            # in the expressions below.
            U[start_date_minus_one] = (
                ON_UP[start_date_minus_one]
                * ON_UP[start_date_minus_two]
                * (q[start_date_minus_one] - q[start_date_minus_two])
            )
            D[start_date_minus_one] = (
                ON_DOWN[start_date_minus_one]
                * ON_DOWN[start_date_minus_two]
                * (q[start_date_minus_one] - q[start_date_minus_two])
            )

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them : turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Enforces eq. (3)
            for t in time_frame:
                model.add_constraint(turned_on[t] <= 1 - OFF[t])
                model.add_constraint(turned_on[t] <= OFF[t - parameters.time_step])
                model.add_constraint(turned_on[t] >= OFF[t - parameters.time_step] - OFF[t])

                # Constraints on turned_off
            # Enforces eq. (5)
            for t in time_frame:
                model.add_constraint(turned_off[t] <= 1 - STOP[t - parameters.time_step])
                model.add_constraint(turned_off[t] <= STOP[t])
                model.add_constraint(turned_off[t] >= STOP[t] - STOP[t - parameters.time_step])

            # stable auxiliary variable
            # Enforces eq. (6)
            for t in time_frame_union_minus_one:
                model.add_constraint(stable[t] <= 1 - ON_FLAT[t - parameters.time_step])
                model.add_constraint(stable[t] <= ON_FLAT[t])
                model.add_constraint(stable[t] >= ON_FLAT[t] - ON_FLAT[t - parameters.time_step])

            # flat_down_stop auxiliary (eq. (22))
            for t in time_frame:
                t_minus_one = t - parameters.time_step
                t_minus_two = t - 2 * parameters.time_step
                model.add_constraint(flat_down_stop[t] <= STOP[t])
                model.add_constraint(flat_down_stop[t] <= ON_DOWN[t_minus_one])
                model.add_constraint(flat_down_stop[t] <= ON_FLAT[t_minus_two])
                model.add_constraint(flat_down_stop[t] >= STOP[t] + ON_DOWN[t_minus_one] + ON_FLAT[t_minus_two] - 2)

            # entered_up and entered_down auxiliaries (defined in sections 6.1.4 and 6.1.5)
            for t in time_frame_union_minus_one:
                # entered_up (eq. (7))
                model.add_constraint(entered_up[t] <= 1 - ON_UP[t - parameters.time_step])
                model.add_constraint(entered_up[t] <= ON_UP[t])
                model.add_constraint(entered_up[t] >= ON_UP[t] - ON_UP[t - parameters.time_step])
                # entered_down (eq. (8))
                model.add_constraint(entered_down[t] <= 1 - ON_DOWN[t - parameters.time_step])
                model.add_constraint(entered_down[t] <= ON_DOWN[t])
                model.add_constraint(entered_down[t] >= ON_DOWN[t] - ON_DOWN[t - parameters.time_step])

            # UP and DOWN auxiliary variables for the gradient.
            # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
            # power output twice in a row, then the second time the gradient is locked.
            # In practice, these variables are defined in two stages

            # First stage : tilde_U and tilde_D
            for t in time_frame:  # Loop in all the time_frame but startDate.
                t_minus_one = t - parameters.time_step
                # tilde_U (eq. (28))
                model.add_constraint(tilde_U[t] <= Q_max * ON_UP[t_minus_one])
                model.add_constraint(tilde_U[t] >= Q_min * ON_UP[t_minus_one])
                model.add_constraint(tilde_U[t] <= q[t] - q[t_minus_one] - Q_min * (1 - ON_UP[t_minus_one]))
                model.add_constraint(
                    tilde_U[t] >= q[t] - q[t_minus_one] - Q_max * (1 - ON_UP[t_minus_one]),
                    "VALUE_of_tilde_UP_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

                # tilde_D (eq. (30))
                model.add_constraint(tilde_D[t] <= Q_max * ON_DOWN[t_minus_one])
                model.add_constraint(tilde_D[t] >= Q_min * ON_DOWN[t_minus_one])
                model.add_constraint(tilde_D[t] <= q[t] - q[t_minus_one] - Q_min * (1 - ON_DOWN[t_minus_one]))
                model.add_constraint(
                    tilde_D[t] >= q[t] - q[t_minus_one] - Q_max * (1 - ON_DOWN[t_minus_one]),
                    "VALUE_of_tilde_DOWN_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Second stage : U and D
            # These variables wil be added to the gradient constraints.
            for t in time_frame:
                # U (eq. (27))
                model.add_constraint(U[t] <= Q_max * ON_UP[t])
                model.add_constraint(U[t] >= Q_min * ON_UP[t])
                model.add_constraint(U[t] <= tilde_U[t] - Q_min * (1 - ON_UP[t]))
                model.add_constraint(
                    U[t] >= tilde_U[t] - Q_max * (1 - ON_UP[t]),
                    "VALUE_of_UP_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )
                # D (eq. (29))
                model.add_constraint(D[t] <= Q_max * ON_DOWN[t])
                model.add_constraint(D[t] >= Q_min * ON_DOWN[t])
                model.add_constraint(D[t] <= tilde_D[t] - Q_min * (1 - ON_DOWN[t]))
                model.add_constraint(
                    D[t] >= tilde_D[t] - Q_max * (1 - ON_DOWN[t]),
                    "VALUE_of_DOWN_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # DD Gradient auxiliary (eq. (23))
            for t in gradients_time_frame:
                t_plus_one = t + parameters.time_step
                model.add_constraint(DD[t] <= Q_max * STOP[t_plus_one])
                model.add_constraint(DD[t] >= Q_min * STOP[t_plus_one])
                model.add_constraint(DD[t] <= D[t] - Q_min * (1 - STOP[t_plus_one]))
                model.add_constraint(
                    DD[t] >= D[t] - Q_max * (1 - STOP[t_plus_one]),
                    "DD_gradient_auxiliary_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in time_frame_union_minus_one:
                # Defined over the whole time frame.
                # Enforces eq. (9)
                model.add_constraint(
                    OFF[t] + ON_UP[t] + ON_DOWN[t] + ON_FLAT[t] + STOP[t] + START[t] == 1,
                    "mutual_exclusion_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

            # Transitions:
            # UP-DOWN and DOWN-UP transitions are forbidden.
            # STOP to ON transitions are also forbidden
            # OFF to STOP transitions
            # START to OFF
            # ON to START
            # START to STOP and STOP to START
            # OFF to ON
            # Finally, we forbid ON_UP to STOP (which never happens in practice) in order
            # to avoid defining a UU auxiliary analoguous to DD.
            for t in time_frame_union_minus_one:
                t_minus_one = t - parameters.time_step
                # Implement eq. (25).
                model.add_constraint(ON_UP[t_minus_one] + ON_DOWN[t] <= 1)
                model.add_constraint(ON_DOWN[t_minus_one] + ON_UP[t] <= 1)
                # STOP to ON (eq. (13))
                model.add_constraint(STOP[t_minus_one] + ON_FLAT[t] <= 1)
                model.add_constraint(STOP[t_minus_one] + ON_DOWN[t] <= 1)
                model.add_constraint(
                    STOP[t_minus_one] + ON_UP[t] <= 1,
                    "transitions_constraints_on_timeFrame_union_minus_one_at_{}".format(
                        Utilities.get_date_to_clean_string(t)
                    ),
                )
            for t in time_frame:
                t_minus_one = t - parameters.time_step
                # ON_UP to STOP transition (eq. (21))
                model.add_constraint(ON_UP[t_minus_one] + STOP[t] <= 1)
                # OFF to STOP (eq. (13)).
                model.add_constraint(OFF[t_minus_one] + STOP[t] <= 1)
                # ON to START (eq. (10))
                model.add_constraint(ON_UP[t_minus_one] + START[t] <= 1)
                model.add_constraint(ON_DOWN[t_minus_one] + START[t] <= 1)
                model.add_constraint(ON_FLAT[t_minus_one] + START[t] <= 1)
                # START to OFF (eq. (11))
                model.add_constraint(START[t_minus_one] + OFF[t] <= 1)
                # START to STOP and STOP to START (eq. (14))
                model.add_constraint(START[t_minus_one] + STOP[t] <= 1)
                model.add_constraint(STOP[t_minus_one] + START[t] <= 1)
                # OFF to ON (eq. (15))
                model.add_constraint(OFF[t_minus_one] + ON_UP[t] <= 1)
                model.add_constraint(OFF[t_minus_one] + ON_FLAT[t] <= 1)
                model.add_constraint(
                    OFF[t_minus_one] + ON_DOWN[t] <= 1,
                    "transitions_constraints_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )
                # The latter constraints are only defined on the time_frame because it does not involve ON variables at the t index.

            # Eviction constraints
            # The unit must leave the STOP state after T_stop time steps.
            # and the START state after T_start time steps.
            for t in time_frame:
                t_minus_T_stop = t - T_stop * parameters.time_step
                t_minus_T_start = t - T_start * parameters.time_step
                # Implements equation (19)
                model.add_constraint(
                    turned_off[t_minus_T_stop] + STOP[t] <= 1,
                    "STOP_eviction_constraint_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )
                # Implements equation (16)
                model.add_constraint(
                    turned_on[t_minus_T_start] + START[t] <= 1,
                    "START_eviction_constraint_at_{}".format(Utilities.get_date_to_clean_string(t)),
                )

                # Mininum time on and minimum time off constraints:
            # if T_on >= 2 or T_off >= 2 or T_stable >= 2, lock the unit in this state.
            if T_on >= 2:
                for t in time_frame_union_minus_one:
                    time_steps = range(1, T_on)  # Corresponds to the set {1,..., T_on - 1}
                    for s in time_steps:
                        # Enforces eq. (31), with T_start > 0
                        t_minus_s_minus_T_start = t - s * parameters.time_step - T_start * parameters.time_step
                        model.add_constraint(
                            turned_on[t_minus_s_minus_T_start] <= ON_UP[t] + ON_DOWN[t] + ON_FLAT[t],
                            "minimum_time_ON_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s_minus_T_start),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_off >= 2:
                for t in time_frame:
                    time_steps = range(1, T_off)  # Corresponds to the set {1,..., T_off - 1}
                    for s in time_steps:
                        # Enforces eq. (32) with T_stop > 0
                        t_minus_s_minus_T_stop = t - s * parameters.time_step - T_stop * parameters.time_step
                        model.add_constraint(
                            turned_off[t_minus_s_minus_T_stop] <= OFF[t],
                            "minimum_time_OFF_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s_minus_T_stop),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_stable >= 2:
                for t in time_frame_union_minus_one:
                    time_steps = range(1, T_stable - 1)  # Corresponds to the set {1,..., T_stable - 2}
                    for s in time_steps:
                        # Enforces eq. (26)
                        t_minus_s = t - s * parameters.time_step
                        model.add_constraint(
                            stable[t_minus_s] <= ON_FLAT[t],
                            "minimum_time_STABLE_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_stop >= 2:
                for t in time_frame:
                    for s in stop_time_steps:
                        t_minus_s = t - s * parameters.time_step
                        # Enforces eq. (24)
                        model.add_constraint(
                            turned_off[t_minus_s] <= STOP[t],
                            "shutdown_ramp_of_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )
            if T_start >= 2:
                for t in time_frame:
                    for s in start_time_steps:
                        t_minus_s = t - s * parameters.time_step
                        # Enforces eq. (17)
                        model.add_constraint(
                            turned_on[t_minus_s] <= START[t],
                            "start_up_ramp_of_{}_at_{}_for_{}".format(
                                thermal_unit.name,
                                Utilities.get_date_to_clean_string(t_minus_s),
                                Utilities.get_date_to_clean_string(t),
                            ),
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Start-up gradient:
            q_min = thermal_unit.minimum_power.max()
            q_step_down = q_min / T_stop
            q_step_up = q_min / T_start

            # Reserves requirements
            # We are in a case where there is a FLAT state, so manual reserves can only be provided
            # when the unit is in the FLAT state.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))
            for t in time_frame:
                # contractedDifference
                model.add_constraint(contracted_difference_up[t] >= reserves_up_procured.get_value(t) - reserves_up[t])
                model.add_constraint(
                    contracted_difference_down[t] >= reserves_down_procured.get_value(t) - reserves_down[t]
                )
                # automatedContractedDifference
                model.add_constraint(
                    automated_contracted_difference_up[t]
                    >= feasible_automated_reserves_up_procured[t] - automated_reserves_up[t]
                )
                model.add_constraint(
                    automated_contracted_difference_down[t]
                    >= feasible_automated_reserves_down_procured[t] - automated_reserves_down[t]
                )

            # Upward and downward "fill up" constraints.
            for t in time_frame:
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    <= q_upper.get_value(t) + parameters.epsilon
                )  # Upward constraint - eq. (41)
                model.add_constraint(
                    q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                    >= q_upper.get_value(t) - parameters.epsilon
                )  # Upward constraint - eq. (41)

                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    <= q_lower.get_value(t) + parameters.epsilon
                )  # Downward constraint - eq. (42)
                model.add_constraint(
                    (
                        q[t]
                        - reserves_down[t]
                        - automated_reserves_down[t]
                        - unprovided_reserves_down[t]
                        + relaxed_reserves[t]
                    )
                    >= q_lower.get_value(t) - parameters.epsilon
                )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            for t in time_frame:
                model.add_constraint(
                    relaxed_reserves[t] <= q_lower.get_value(t) * (1 - ON_UP[t] - ON_FLAT[t] - ON_DOWN[t])
                )

            # impossible commitment and stable reserves constraints (eqs. (44) and (45))
            for t in time_frame:
                model.add_constraint(automated_reserves_up[t] <= maximum_automated * (1 - OFF[t] - START[t] - STOP[t]))
                model.add_constraint(
                    automated_reserves_down[t] <= maximum_automated * (1 - OFF[t] - START[t] - STOP[t])
                )
                model.add_constraint(
                    reserves_up[t] <= q_upper.get_value(t) * (1 - ON_UP[t] - ON_DOWN[t] - OFF[t] - START[t] - STOP[t])
                )
                # for compacity, implements both eq (44) and (45)
                model.add_constraint(
                    reserves_down[t] <= q_upper.get_value(t) * (1 - ON_UP[t] - ON_DOWN[t] - OFF[t] - START[t] - STOP[t])
                )

            # Power output
            for t in time_frame:
                model.add_constraint(
                    q[t]
                    >= q_lower.get_value(t) * (ON_UP[t] + ON_DOWN[t] + ON_FLAT[t])
                    + turned_off[t] * (q_min - q_step_down),
                    "lower_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Lower bound (eq. (33))
                model.add_constraint(
                    q[t]
                    <= q_upper.get_value(t) * (ON_UP[t] + ON_DOWN[t] + ON_FLAT[t])
                    + (STOP[t] + START[t]) * q_min
                    - turned_off[t] * q_step_down,
                    "upper_bound_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                )  # Upper bound (eq. (34))

            # Power gradients
            if delta_q > 0:  # Case where the gradient is finite.
                for t in gradients_time_frame:  # The gradients are defined only up to T-1.
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. (35))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= (
                            delta_q * entered_up[t]
                            + U[t]
                            + D[t]
                            - q_step_down * turned_off[t_next]
                            - STOP[t] * q_step_down
                            + q_step_up * turned_on[t_next]
                            + START[t] * q_step_up
                            - DD[t]
                        ),
                        "upward_gradient_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (37))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= (
                            -delta_q * entered_down[t]
                            + U[t]
                            + D[t]
                            - q_step_down * turned_off[t_next]
                            - STOP[t] * q_step_down
                            + flat_down_stop[t_next] * delta_q
                            - DD[t]
                            + q_step_up * turned_on[t_next]
                            + START[t] * q_step_up
                        ),
                        "downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient

            elif delta_q == 0:  # Case where the gradient is 'infinite'
                for t in gradients_time_frame:
                    t_next = t + parameters.time_step  # Get the next time step

                    # Upward unconstrained gradient (eq. (36))
                    model.add_constraint(
                        q[t_next] - q[t]
                        <= (
                            delta_q_unconstrained * entered_up[t]
                            + U[t]
                            + D[t]
                            - q_step_down * turned_off[t_next]
                            - STOP[t] * q_step_down
                            + q_step_up * turned_on[t_next]
                            + START[t] * q_step_up
                            - DD[t]
                        ),
                        "upward_gradient_of_{}_at_{}".format(thermal_unit.name, Utilities.get_date_to_clean_string(t)),
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (38))
                    model.add_constraint(
                        q[t_next] - q[t]
                        >= (
                            -delta_q_unconstrained * entered_down[t]
                            + U[t]
                            + D[t]
                            - q_step_down * turned_off[t_next]
                            - STOP[t] * q_step_down
                            + flat_down_stop[t_next] * delta_q_unconstrained
                            - DD[t]
                            + q_step_up * turned_on[t_next]
                            + START[t] * q_step_up
                        ),
                        "downward_gradient_of_{}_at_{}".format(
                            thermal_unit.name, Utilities.get_date_to_clean_string(t)
                        ),
                    )  # Downward gradient

            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    "*** WARNING ***\n No gradients have been defined for equipment {}. \n "
                    "Please check the value of `maximum_gradient`.".format(thermal_unit.name)
                )
                raise ValueError("Missing gradients for thermic units.")

                # Energy limits
            if thermal_unit.has_daily_energy_constraint:
                days_in_time_frame = []

                for local_time in time_frame:
                    if datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0) not in days_in_time_frame:
                        days_in_time_frame.append(datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0))

                for date in days_in_time_frame:
                    upper_bound = thermal_unit.maximum_daily_energy.get_value(date)

                    matching_steps = []
                    for local_time in time_frame:
                        if (
                            (local_time.year == date.year)
                            and (local_time.month == date.month)
                            and (local_time.day == date.day)
                        ):
                            matching_steps.append(local_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        model.add_constraint(
                            sum(q[t] for t in matching_steps)
                            <= upper_bound * parameters.time_step / 1440.0 * len(matching_steps),
                            "energy_limit_of_{}_at_{}".format(
                                thermal_unit.name, Utilities.get_date_to_clean_string(date)
                            ),
                        )
                        # TimeStep / 1440 * len(matching_steps) is a converting factor

        ###############
        #
        # STEP 4 : Solving the problem
        #
        ###############

        model.set_solver_specific_parameters_as_string(
            "MIPRELSTOP {} PRESOLVE {} MAXTIME {}".format(
                parameters.duality_gap, int(parameters.presolve), parameters.time_out
            )
        )
        if parameters.debug:
            lp_file_name = os.path.join(
                parameters.output_folder, "{}_price_{}.lp".format(thermal_unit.name, price_type)
            )
            model.export_model(lp_file_name)

        model.solve(parameters.solver_time_out.total_minutes())

        ###############
        #
        # STEP 5 : Return the results
        #
        ###############

        # Export the results
        # Final step : export the results of the program. We initialize a dictionnary that will store the results.
        # This dictionnary is returned to the user.
        # Initialize the dictionnary
        results = {}

        # Power output
        q_star = Timeseries.from_index(parameters.start_date, parameters.timestep, parameters.end_date, default_value=0)

        results["q"] = {}
        for t in time_frame:
            q_star[t] = q[t].solution_value()

        # If verbose is activated, inform the user if the optimal program is such that the unit
        # provides no output
        if parameters.verbose:
            if abs(q_star.min() - 0.0) <= 1e-6 and abs(q_star.max() - 0.0) <= 1e-6:
                zero_output_message = """*** Info ***
                The optimal solution for the unit {} is such that the unit remains offline and
                delivers no power output.
                """.format(thermal_unit.name)
                cfg.logger.info(zero_output_message)

        # contractedDifference.
        # This variable is returned as together with the procuredReserves it allows to know the exact amount
        # of reserves supplied (and unsupplied) for each time step. the reserves variables can take inexact values on the time steps
        # where there is no reserve to provide due to the fill up constraints.
        # Create the time series
        contracted_difference_up_star = Timeseries.from_index(
            parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
        )
        contracted_difference_down_star = Timeseries.from_index(
            parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
        )
        # Initialize the dictionnary keys
        results["contracted_difference_up"] = {}
        results["contracted_difference_down"] = {}
        # Add the automatedDifference
        # Create the time series
        automated_contracted_difference_up_star = Timeseries.from_index(
            parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
        )
        automated_contracted_difference_down_star = Timeseries.from_index(
            parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
        )
        # Initialize the dictionnary keys
        results["automated_contracted_difference_up"] = {}
        results["automated_contracted_difference_down"] = {}
        # Populate the time series
        for t in time_frame:
            contracted_difference_up_star[t] = contracted_difference_up[t].solution_value()
            contracted_difference_down_star[t] = contracted_difference_down[t].solution_value()
        # Populate the automatedDifference time series
        for t in time_frame:
            automated_contracted_difference_up_star[t] = automated_contracted_difference_up[t].solution_value()
            automated_contracted_difference_down_star[t] = automated_contracted_difference_down[t].solution_value()

        # Populate the dictionnary
        results["q"] = q_star
        results["contracted_difference_up"] = contracted_difference_up_star
        results["contracted_difference_down"] = contracted_difference_down_star
        # Add the automatedDifference
        results["automated_contracted_difference_up"] = automated_contracted_difference_up_star
        results["automated_contracted_difference_down"] = automated_contracted_difference_down_star

        # Status and auxiliary variables
        # Permanent variables
        ON_UP_star = Timeseries.from_index(
            parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
        )
        ON_DOWN_star = Timeseries.from_index(
            parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
        )
        OFF_star = Timeseries.from_index(
            parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
        )

        # Initialize the corresponding keys in the dictionnary
        results["ON_UP"] = {}
        results["ON_DOWN"] = {}
        results["OFF"] = {}

        # Populate the time series
        for t in time_frame:
            ON_UP_star[t] = ON_UP[t].solution_value()
            ON_DOWN_star[t] = ON_DOWN[t].solution_value()
            OFF_star[t] = OFF[t].solution_value()

        # Populate the dictionnary
        results["ON_UP"] = ON_UP_star
        results["ON_DOWN"] = ON_DOWN_star
        results["OFF"] = OFF_star

        # Conditional variables
        if T_start >= 1:
            START_star = Timeseries.from_index(
                parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
            )
            # Add the keys in the dictionnary
            results["START"] = {}
            for t in time_frame:
                START_star[t] = START[t].solution_value()
                # Add the time series to the dictionnary.
            results["START"] = START_star
        if T_stop >= 1:
            STOP_star = Timeseries.from_index(
                parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
            )
            results["STOP"] = {}
            for t in time_frame:
                STOP_star[t] = STOP[t].solution_value()
            # Add the time series to the dictionnary.
            results["STOP"] = STOP_star
        if T_stable >= 1:
            ON_FLAT_star = Timeseries.from_index(
                parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
            )
            results["ON_FLAT"] = {}
            for t in time_frame:
                ON_FLAT_star[t] = ON_FLAT[t].solution_value()
            results["ON_FLAT"] = ON_FLAT_star

        return results
