"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.timing import generate_datetimes


# Contains miscellaneous functions used in the various files.
class Utilities:
    @staticmethod
    def get_date_to_clean_string(date: DateTime) -> str:
        """Converts a datetime object to a string without special characters"""
        return date.format("YYYY_MM_DD_HH_mm_SS")

    @staticmethod
    def define_orders_time(parameters: DayAheadOrdersParameters) -> list[DateTime]:
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
                parameters.end_date.subtract(minutes=parameters.time_step),
                pendulum.duration(minutes=parameters.time_step),
            )
        else:
            msg = "The EndDate parameter must be posterior to the StartDate parameter."
            cfg.logger.error(msg)
        return orders_time
