"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import datetime

from atlas import Timeseries


class DAOTimeseries(Timeseries):
    """wrapper class for Timeseries in order to add utilities functions"""

    def set_or_add_value(self, time: datetime | str, value: float) -> None:
        """
        set a value to the timeseries or add it if it doesn't exist
        :param time: the time index
        :type time: datetime
        :param value: the value to add
        :type value: float
        :return: None
        """
        if time in self:
            self.set_value(time, value)
        else:
            self.add_index(time, value)
