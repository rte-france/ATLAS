"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import datetime
import os
import sys

from atlas import Logger


## NB. sys will not be used in the future. Instead, use a function that interrupts the system.
## once this is implemented, remove the


# Contains miscellaneous functions used in the various files.
class Utilities:
    def datetime_parser(DateString):
        """
        Converts a string into a variable in DateTime format.
        Returns a detailed error if the conversion fails.
        Arguments:
        - `DateString`: a date (dd/mm/yyy - hh:mm:ss) in string format
        """

        try:
            result_date = API.DatetimeIndex.ParseDate(DateString)
        except SystemError:
            msg = "One of the dates entered cannot be converted. Please check that the format is in correct form (e.g. 'dd/mm/yyy hh:mm:ss')"
            API.IO.Trace.Log(msg, API.IO.LogTypeError)
            sys.exit()  ### FUTURE WARNING : WILL HAVE TO BE REPLACED BY AN API FUNCTION THAT STOPS THE EXECUTION OF THE PROGRAM ASAP
        return result_date

    def get_date_to_clean_string(self, date: datetime) -> str:
        """Converts a datetime object to a string without special characters"""
        return datetime.strftime(date, "%d_%m_%Y %H_%M_%S")

    def define_orders_time(p) -> list[datetime]:
        """
        This function creates a sequence of timestamps between a startDate and a endDate
        with step deltaTime. It returns a list of dateTime objects.
        In particular, it makes sure that no time step crosses the endDate boundary.

        Arguments:
        - `p` a named tuple of subclass Parameters_List containing the dates.
        """

        if p.start_date < p.end_date:
            orders_time = Utilities.new_index(p.start_date, p.end_date.AddMinutes(-p.time_step), str(p.time_step) + "m")
        else:
            msg = "The EndDate parameter must be posterior to the StartDate parameter."
            Logger.get_logger().error(msg)
            # sys.exit()
        return orders_time

    @staticmethod
    def new_index(start_date: datetime, end_date: datetime, interval: datetime.timedelta) -> list[datetime]:
        """
        Generate a list of datetime between `start` and `end` depending on the given interval.

        :param start_date: first datetime
        :param end_date: last datetime
        :param interval: time interval (timedelta)
        :return: datetime list
        """
        if start_date >= end_date:
            raise ValueError("start date must be before end date.")

        result = []
        current = start_date
        while current <= end_date:
            result.append(current)
            current = current + interval

        return result

    def QuickerGetForecast(matrix, execution_date, start_date, end_date):
        """
        This function is created to limit calls to the GetForecast method which is time-expensive.
        If conditions are met, the far quicker GetTimeSeries method is called

        Arguments:
        - `matrix` a Forecasting Matrix
        - `execution_date` the desired reference date within
        - `start_date` the start date to crop the ts with (to limit its size), if GetForecast is called
        - `end_date` the end date to crop the ts with (to limit its size), if GetForecast is called
        """
        if execution_date in matrix.Index:
            # An Extract between start_date and end_date might be necessary here, but not usefull as of ATLAS 1.2
            return matrix.GetTimeSeries(execution_date)

        return matrix.GetForecast(execution_date, start_date, end_date)

    # Helper used to manage the output path of debug data
    def check_output_path(output_path):
        """
        Takes as input a path (in our case, in the SAMBA output folder of the user),
        and checks if this path exists.
        If not, a folder is created and the user is notified with a message in the console
        """

        if not os.path.exists(output_path):
            os.mkdir(output_path)
            API.IO.Trace.Log("Output folder for debug created at {}".format(output_path), API.IO.LogTypeInfo)

        return None
