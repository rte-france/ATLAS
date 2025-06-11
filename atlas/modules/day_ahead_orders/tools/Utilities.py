"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import datetime

import pendulum

from atlas import Logger
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.timing import generate_datetimes


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
            orders_time = generate_datetimes(
                parameters.start_date,
                parameters.end_date - pendulum.duration(minutes=parameters.time_step),
                pendulum.duration(minutes=parameters.time_step),
            )
        else:
            msg = "The EndDate parameter must be posterior to the StartDate parameter."
            Logger.get_logger().error(msg)
        return orders_time
