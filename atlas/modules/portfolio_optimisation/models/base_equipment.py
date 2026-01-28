"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime, Duration

from atlas.timing import generate_datetimes


class BaseEquipmentPO:
    """Base class for Portfolio Optimisation equipment models with common functionality."""

    def get_optimisation_time_window(
        self, start_date: DateTime, end_date: DateTime, timestep: Duration
    ) -> list[DateTime]:
        """
        Get optimisation time windows based on additional hours.

        :param start_date: Start date for optimization window
        :type start_date: DateTime
        :param end_date: End date for optimization window
        :type end_date: DateTime
        :param timestep: Time step duration
        :type timestep: Duration
        :return: List of datetime objects representing the optimization time window
        :rtype: list[DateTime]
        """

        self.optimisation_time_window = generate_datetimes(
            start=start_date,
            end=end_date + self.additional_hours,  # type: ignore  [attr-defined]
            freq=timestep,
        )
        return self.optimisation_time_window
