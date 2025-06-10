"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import datetime, timedelta

from atlas import Logger
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters


# Contains miscellaneous functions used in the various files.
class Utilities:
    @staticmethod
    def get_date_to_clean_string(date: datetime) -> str:
        """Converts a datetime object to a string without special characters"""
        return datetime.strftime(date, "%d_%m_%Y %H_%M_%S")

    @staticmethod
    def define_orders_time(parameters: DayAheadOrdersParameters) -> list[datetime]:
        """
        This function creates a sequence of timestamps between a startDate and a endDate
        with step deltaTime. It returns a list of dateTime objects.
        In particular, it makes sure that no time step crosses the endDate boundary.

        Arguments:
        - `parameters` an instance of DayAheadOrdersParameters.
        """
        orders_time = []
        if parameters.start_date < parameters.end_date:
            orders_time = Utilities.new_index(
                parameters.start_date,
                parameters.end_date - timedelta(minutes=parameters.time_step),
                timedelta(minutes=parameters.time_step),
            )
        else:
            msg = "The EndDate parameter must be posterior to the StartDate parameter."
            Logger.get_logger().error(msg)
        return orders_time

    @staticmethod
    def new_index(start_date: datetime, end_date: datetime, interval: timedelta) -> list[datetime]:
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
