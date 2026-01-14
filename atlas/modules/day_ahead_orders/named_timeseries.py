"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import Timeseries
from atlas.modules.day_ahead_orders.dao_timeseries import DAOTimeseries


class NamedTimeseries(DAOTimeseries):
    def __init__(self, name: str, timeseries: Timeseries):
        """
        :param name: the name of the timeseries
        :type name: str
        :param timeseries: the timeseries
        :type timeseries: Timeseries
        """
        super().__init__(timeseries)
        self.name = name
