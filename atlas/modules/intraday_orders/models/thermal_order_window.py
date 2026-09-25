"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import Timeseries
from atlas.modules.intraday_orders.models.enums import WindowType


class ThermalOrderWindow(Timeseries):
    def __init__(
        self,
        timeseries: Timeseries,
        window_type: WindowType,
        timezone: str = "UTC",
    ) -> None:
        """
        :param timeseries: The input Timeseries data.
        :type timeseries: pl.DataFrame or Timeseries
        :param timezone: Timezone string used to convert datetime values, defaults to "UTC"
        :type timezone: str, optional
        """
        super().__init__(timeseries, timezone)
        self.__window_type = window_type

    @property
    def window_type(self) -> WindowType:
        return self.__window_type
