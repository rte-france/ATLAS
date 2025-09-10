"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math
import atlas.config as cfg
from atlas.modules.day_ahead_orders.tools.Utilities import Utilities
from atlas.math.timeseries import Timeseries
from atlas import generate_datetimes
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

                # TODO
                # # Store state sequences in the output marker
                # local_time_index = res["OFF"].index()
                # new_sequence_ts = API.TimeSeries.NewTimeSeries(
                #     f"State_sequence_of_{unit..name}_{value}_price",
                #     API.TimeSeries.Constant,
                #     "Integer",
                #     local_time_index,
                #     0,
                # )
                #
                # for time in local_time_index:
                #     if res["ON_UP"].get_value(time) == 1:
                #         new_sequence_ts.SetValue(time, 1)
                #         continue
                #
                #     if res["ON_DOWN"].get_value(time) == 1:
                #         new_sequence_ts.SetValue(time, 2)
                #         continue
                #
                #     if res["OFF"].get_value(time) == 1:
                #         new_sequence_ts.SetValue(time, 3)
                #         continue
                #
                #     if "START" in res.keys():
                #         if res["START"].get_value(time) == 1:
                #             new_sequence_ts.SetValue(time, 4)
                #             continue
                #
                #     if "STOP" in res.keys():
                #         if res["STOP"].get_value(time) == 1:
                #             new_sequence_ts.SetValue(time, 5)
                #             continue
                #
                #     if "ON_FLAT" in res.keys():
                #         if res["ON_FLAT"].get_value(time) == 1:
                #             new_sequence_ts.SetValue(time, 6)
                #             continue
                #
                # unit.StateSequence.AddTimeSeries(
                #     f"{Utilities.get_date_to_clean_string(parameters.execution_date)}-{value.upper()}_DAO",
                #     new_sequence_ts,
                # )

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
            T_on = int(max(1, math.ceil(thermal_unit.minimum_time_on * 60 / parameters.time_step))) + 1
        else:
            T_on = 0

        if thermal_unit.minimum_time_off > 0:
            T_off = int(max(1, math.ceil(thermal_unit.minimum_time_off * 60 / parameters.time_step))) + 1
        else:
            T_off = 0
        T_start = int(math.floor(thermal_unit.startup_duration * 60 / parameters.time_step))
        T_stop = int(math.floor(thermal_unit.shutdown_duration * 60 / parameters.time_step))

        if minimum_stable_power_duration * 60 >= parameters.time_step:
            T_stable = int(math.ceil(minimum_stable_power_duration * 60 / parameters.time_step)) + 1
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

        # TODO

        return None
