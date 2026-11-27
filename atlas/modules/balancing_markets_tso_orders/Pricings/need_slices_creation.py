"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math

import atlas.config as cfg
from atlas import AbstractTimeseries, Timeseries
from atlas.modules.balancing_markets_tso_orders import utils
from atlas.modules.balancing_markets_tso_orders.parameters import TSOOrdersParameters


# Function creating slices with no volume risk aversion
def basic_slice_creation(total_needs_timeseries: AbstractTimeseries, parameters: TSOOrdersParameters):
    """
    Create slices according to the maximum slice size parameter.
    When possible, all slices are constructed to be at the maximum size.
    However, the priority is to create slices of the same size across all time steps.
    In addition, if both positive and negative needs are encountered in the same time frame,
    the negative parts are treated separately.
    """

    # Setup useful dictionaries
    balancing_needs_dictionary = {}
    stack_energy_dictionary = {}
    slices_sizes_dictionary = {}
    extremum_times_dictionary = {}

    # Initialize the slice_number
    slice_number = 0

    # Divide the need timeseries between its negative and positive values
    positive_needs_timeseries = Timeseries.from_timeseries(total_needs_timeseries)
    negative_needs_timeseries = Timeseries.from_timeseries(total_needs_timeseries)

    for time in total_needs_timeseries:
        if total_needs_timeseries.get_value(time) < 0:
            positive_needs_timeseries.set_value(time, 0)
        else:
            negative_needs_timeseries.set_value(time, 0)

    # Negative part first
    if negative_needs_timeseries.min() < 0:
        # Search for the minima of negative_needs_timeseries, and for the times when these minima occur
        current_minimum, current_minimum_times = utils.get_extremum_and_times(negative_needs_timeseries, "minimum")

        # If the imbalance is too large compared to the slice size, it can create too many optimizations.
        # It is then bounded to 10 here.
        # TODO: Clean this

        # The slice size is fixed outside of parameters, since it may be modified
        pricing_slices_size = parameters.pricing_slices_size

        if abs(current_minimum) / pricing_slices_size >= 10:
            pricing_slices_size = int(math.ceil(abs(current_minimum) / 1000.0) * 100)

            cfg.logger.warning(
                f"The slices size was too small for market at {str(parameters.temporal.execution_date)}. \nIt was adjusted to {str(pricing_slices_size)}"
            )

        # Loop over negative_needs_timeseries, by removing the minimum between pricing_slices_size and
        # (current_minimum - second_minimum) to times when the current minimum is reached
        # It is done this way to limit the number of balancing optimizations runs.
        # All of the following part are only required if the need timeseries is not equal to 0 all the time
        if abs(current_minimum) > 0:
            # Initialize empty_needs_tracker spotters
            null_needs_tracker = 0

            while not null_needs_tracker:
                if abs(current_minimum) <= 0:
                    null_needs_tracker = 1

                slice_number += 1

                # Store the balancing needs timeseries corresponding to the current stack
                balancing_needs_dictionary[slice_number] = Timeseries.from_timeseries(negative_needs_timeseries)

                # Compute the total energy of the current stack
                stack_energy_dictionary[slice_number] = negative_needs_timeseries * parameters.temporal.timestep.hours

                # Store the current maximum times in extremum_times_dictionary
                extremum_times_dictionary[slice_number] = current_minimum_times

                # Create a timeseries storing the size of needs for each time step for the current slice
                slices_sizes_dictionary[slice_number] = Timeseries.from_timeseries(negative_needs_timeseries)
                for time in slices_sizes_dictionary[slice_number]:
                    slices_sizes_dictionary[slice_number].set_value(time, 0)

                # Compute the value that will be subtracted from negative_needs_timeseries for times
                # when the current_minimum is reached, according to.pricing_slices_size
                second_minimum = utils.get_second_extremum(negative_needs_timeseries, current_minimum_times, "minimum")

                if current_minimum - second_minimum == 0:
                    substracted_value = min(pricing_slices_size, abs(current_minimum))
                else:
                    substracted_value = min(pricing_slices_size, abs(current_minimum - second_minimum))

                # Remove a slice from the need TimeSeries for times when the current_maximum is reached
                for time in current_minimum_times:
                    # Remove a slice from the need TimeSeries for times when the current_maximum is reached
                    negative_needs_timeseries.set_value(
                        time, negative_needs_timeseries.get_value(time) + substracted_value
                    )

                    slices_sizes_dictionary[slice_number].set_value(time, -substracted_value)

                current_minimum, current_minimum_times = utils.get_extremum_and_times(
                    negative_needs_timeseries, "minimum"
                )

    # Small required adjustment for slice_number, because of the implementation method
    if slice_number > 0:
        slice_number += -1

    # Then, positive part
    if positive_needs_timeseries.max() > 0:
        # Search for the maxima of positive_needs_timeseries, and for the times when these maxima occur
        current_maximum, current_maximum_times = utils.get_extremum_and_times(positive_needs_timeseries, "maximum")

        # If the imbalance is too large compared to the slice size, it can create too many optimizations.
        # It is then bounded to 10 here.
        # TODO: Clean this

        # The slice size is fixed outside of parameters, since it may be modified
        pricing_slices_size = parameters.pricing_slices_size

        if abs(current_maximum) / pricing_slices_size >= 10:
            pricing_slices_size = int(math.ceil(abs(current_maximum) / 1000.0) * 100)

            cfg.logger.warning(
                f"The slices size was too small for market at {str(parameters.temporal.execution_date)}. \nIt was adjusted to {str(pricing_slices_size)}"
            )

        # Loop over positive_needs_timeseries, by removing the minimum between pricing_slices_size and
        # (current_maximum - second_maximum) to times when the current maximum is reached
        # It is done this way to limit the number of balancing optimizations runs.
        # All of the following part are only required if the need timeseries is not equal to 0 all the time
        if abs(current_maximum) > 0:
            # Initialize empty_needs_tracker spotters
            null_needs_tracker = 0

            while not null_needs_tracker:
                if current_maximum <= 0:
                    null_needs_tracker = 1

                slice_number += 1

                # Store the balancing needs timeseries corresponding to the current stack
                balancing_needs_dictionary[slice_number] = Timeseries.from_timeseries(positive_needs_timeseries)

                # Compute the total energy of the current stack
                stack_energy_dictionary[slice_number] = positive_needs_timeseries * parameters.temporal.timestep.hours

                # Store the current maximum times in extremum_times_dictionary
                extremum_times_dictionary[slice_number] = current_maximum_times

                # Create a timeseries storing the size of needs for each time step for the current slice
                slices_sizes_dictionary[slice_number] = Timeseries.from_timeseries(positive_needs_timeseries)
                for time in slices_sizes_dictionary[slice_number]:
                    slices_sizes_dictionary[slice_number].set_value(time, 0)

                # Compute the value that will be subtracted from positive_needs_timeseries for times
                # when the current_maximum is reached, according to.pricing_slices_size
                second_maximum = utils.get_second_extremum(positive_needs_timeseries, current_maximum_times, "maximum")

                if current_maximum - second_maximum == 0:
                    substracted_value = min(pricing_slices_size, current_maximum)
                else:
                    substracted_value = min(pricing_slices_size, current_maximum - second_maximum)

                # Remove a slice from the need TimeSeries for times when the current_maximum is reached
                for time in current_maximum_times:
                    # Remove a slice from the need TimeSeries for times when the current_maximum is reached
                    positive_needs_timeseries.set_value(
                        time, positive_needs_timeseries.get_value(time) - substracted_value
                    )

                    slices_sizes_dictionary[slice_number].set_value(time, substracted_value)

                current_maximum, current_maximum_times = utils.get_extremum_and_times(
                    positive_needs_timeseries, "maximum"
                )

    # Return results
    return balancing_needs_dictionary, stack_energy_dictionary, slices_sizes_dictionary, extremum_times_dictionary


# Function creating slices with volume risk aversion considered
def volume_uncertainty_slice_creation(total_needs_timeseries: AbstractTimeseries, parameters: TSOOrdersParameters):
    """
    Takes as input the timeseries of balancing needs total_needs_timeseries,
    and returns dictionaries containing:
    _ The quantiles associated with total_needs_timeseries balancing forecasts,
      based on the error distribution quantiles in the tso_error_quantiles csv given in parameters.
    _ The size of all slices of needs based on the quantiles dictionary.
      Slices are usually identical to quantiles, except for limit values.
    """

    # Retrieve the abacus giving the slice division as a function of balancing_needs
    f = open(parameters.tso_error_quantiles)
    csv_lines = f.readlines()
    f.close()
    linear_reg_slopes = {}
    linear_reg_intersects = {}

    for line_enum, line in enumerate(csv_lines):
        if line_enum == 0:
            continue

        line_values = line.split(";")
        linear_reg_slopes[float(line_values[0].replace(",", "."))] = float(line_values[1].replace(",", "."))
        linear_reg_intersects[float(line_values[0].replace(",", "."))] = float(line_values[2].replace(",", "."))

    alpha_list = sorted(linear_reg_slopes.keys())

    quantiles_dictionary = {}
    slices_sizes_dictionary = {}

    end_date = parameters.temporal.end_date - parameters.temporal.timestep
    for alpha in alpha_list:
        quantiles_dictionary[alpha] = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, end_date, default_value=0
        )
        slices_sizes_dictionary[alpha] = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, end_date, default_value=0
        )

    # Compute the size of each slice, depending on the case between:
    # - Case 1: Slices needs are always positive (i.e. upward needs)
    # - Case 2: Slices needs are always negative (i.e. downward needs)
    # - Case 3: Some slices are negative while other are positive

    for time in total_needs_timeseries:
        # Fill the quantile dictionary first
        for alpha in alpha_list:
            quantiles_dictionary[alpha].set_value(
                time, total_needs_timeseries.get_value(time) * linear_reg_slopes[alpha] + linear_reg_intersects[alpha]
            )

        # Case 1
        if total_needs_timeseries.get_value(time) > 0 and (
            total_needs_timeseries.get_value(time) * linear_reg_slopes[0.1] + linear_reg_intersects[0.1] >= 0
        ):
            for alpha_enum, alpha in enumerate(alpha_list):
                # For alpha = 0.01, slice size is 0
                if alpha == 0.01:
                    continue

                # Special case for alpha = 0.1
                if alpha == 0.1:
                    slices_sizes_dictionary[alpha].set_value(
                        time,
                        total_needs_timeseries.get_value(time) * linear_reg_slopes[alpha]
                        + linear_reg_intersects[alpha],
                    )
                    continue

                # Regular case
                alpha_prev = alpha_list[alpha_enum - 1]
                slices_sizes_dictionary[alpha].set_value(
                    time, linear_reg_intersects[alpha] - linear_reg_intersects[alpha_prev]
                )
        # Case 2
        elif total_needs_timeseries.get_value(time) < 0 and (
            total_needs_timeseries.get_value(time) * linear_reg_slopes[0.9] + linear_reg_intersects[0.9] <= 0
        ):
            for alpha_enum, alpha in enumerate(alpha_list):
                # For alpha = 0.99, slice size is 0
                if alpha == 0.99:
                    continue

                # Special case for alpha = 0.9
                if alpha == 0.9:
                    slices_sizes_dictionary[alpha].set_value(
                        time,
                        total_needs_timeseries.get_value(time) * linear_reg_slopes[alpha]
                        + linear_reg_intersects[alpha],
                    )
                    continue

                # Regular case
                alpha_next = alpha_list[alpha_enum + 1]
                slices_sizes_dictionary[alpha].set_value(
                    time, linear_reg_intersects[alpha] - linear_reg_intersects[alpha_next]
                )
        # Case 3
        else:
            alpha_switch_1 = 0
            alpha_switch_2 = 0

            for alpha_enum, alpha in enumerate(alpha_list):
                if alpha == 0.01:
                    slices_sizes_dictionary[alpha].set_value(
                        time, linear_reg_intersects[alpha] - linear_reg_intersects[0.1]
                    )
                    continue

                if alpha == 0.99:
                    slices_sizes_dictionary[alpha].set_value(
                        time, linear_reg_intersects[alpha] - linear_reg_intersects[0.9]
                    )
                    continue

                # Regular alphas. Find the slice where needs switch from negative to positive values, and store them in switch variables
                alpha_prev = alpha_list[alpha_enum - 1]
                alpha_next = alpha_list[alpha_enum + 1]
                if (
                    total_needs_timeseries.get_value(time) * linear_reg_slopes[alpha] + linear_reg_intersects[alpha] < 0
                ) and (
                    total_needs_timeseries.get_value(time) * linear_reg_slopes[alpha_next]
                    + linear_reg_intersects[alpha_next]
                    > 0
                ):
                    alpha_switch_1 = alpha
                    alpha_switch_2 = alpha_next

                    slices_sizes_dictionary[alpha].set_value(
                        time,
                        total_needs_timeseries.get_value(time) * linear_reg_slopes[alpha]
                        + linear_reg_intersects[alpha],
                    )
                    slices_sizes_dictionary[alpha_next].set_value(
                        time,
                        total_needs_timeseries.get_value(time) * linear_reg_slopes[alpha_next]
                        + linear_reg_intersects[alpha_next],
                    )
                    continue

                # Skip alpha_switch_2 as it was already previously filled
                if alpha == alpha_switch_2:
                    continue

                # For all other values of alpha,  the slice size depends on the position relative to alpha_switch_1 (and alpha_switch_2)
                # If we are below alpha_switch_1
                if alpha_switch_1 == 0:
                    slices_sizes_dictionary[alpha].set_value(
                        time, linear_reg_intersects[alpha] - linear_reg_intersects[alpha_next]
                    )
                # If we are below alpha_switch_2
                else:
                    slices_sizes_dictionary[alpha].set_value(
                        time, linear_reg_intersects[alpha] - linear_reg_intersects[alpha_prev]
                    )

    return quantiles_dictionary, slices_sizes_dictionary
