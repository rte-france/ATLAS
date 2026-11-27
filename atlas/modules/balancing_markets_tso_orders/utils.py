"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import AbstractTimeseries, Timeseries


def datetime_to_instance_name_string(datetime):
    """
    Takes a DateTime as input and returns a string with no special character, that can be used within an instance name
    Example : If the input is DateTime(2028, 01, 01, 10, 30, 00), i.e. "01/01/2028 10:30:00", the string output will be 2028_01_01_10_30_00
    """
    return (
        str(datetime)[6:10]
        + "_"
        + str(datetime)[3:5]
        + "_"
        + str(datetime)[0:2]
        + "_"
        + str(datetime)[11:13]
        + "_"
        + str(datetime)[14:16]
        + "_"
        + str(datetime)[17:19]
    )


# Function identifying the maximum of a TimeSeries and giving the time(s) of this (these) maximum(s)
def get_extremum_and_times(timeseries: AbstractTimeseries, direction):
    """
    Takes a TimeSeries as input and returns its maximum or minimum,
    depending on direction argument (possible values are 'minimum' and 'maximum'),
    and the times of these extremums.
    """

    extremum_times = []
    current_extremum = timeseries.get_by_index(0)

    for time in timeseries:
        local_value = timeseries.get_value(time)

        if local_value == current_extremum:
            extremum_times.append(time)

        else:
            if direction == "minimum":
                if local_value < current_extremum:
                    extremum_times = []
                    extremum_times.append(time)
                    current_extremum = local_value

            if direction == "maximum":
                if local_value > current_extremum:
                    extremum_times = []
                    extremum_times.append(time)
                    current_extremum = local_value

    return current_extremum, extremum_times


# Function identifying the second-highest value of a TimeSeries, used in certain Pricing types
def get_second_extremum(timeseries: AbstractTimeseries, first_extremum_times, direction):
    """
    Takes as inputs a TimeSeries and the list of times when it reaches its extremum value,
    according to the direction. Return the value of the second extremum of this TimeSeries.
    """
    local_timeseries = Timeseries.from_timeseries(timeseries)

    for time in first_extremum_times:
        local_timeseries.set_value(time, 0)

    second_extremum, unused_variable = get_extremum_and_times(local_timeseries, direction)

    return second_extremum
