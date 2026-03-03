"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import datetime

import pandas as pd
import polars as pl

from atlas import Timeseries
from atlas.type import TimeseriesDict


class DAOTimeseries(Timeseries):
    """wrapper class for Timeseries in order to add utilities functions"""

    name: str

    def __init__(
        self,
        timeseries: pl.DataFrame | Timeseries | pd.DataFrame | TimeseriesDict | None = None,
        timezone: str = "UTC",
        name: str = "",
    ):
        """
        :param timeseries: the timeseries
        :type timeseries: pl.DataFrame | Timeseries | pd.DataFrame | TimeseriesDict
        :param timezone: the timezone to use
        :type timezone: str
        :param name: the name of the timeseries
        :type name: str
        """
        super().__init__(timeseries, timezone)
        self.name = name

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
