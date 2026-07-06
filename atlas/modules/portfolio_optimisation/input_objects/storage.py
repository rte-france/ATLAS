"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas.common.optimal_dispatch.input_objects.storage import StorageDispatchInput
from atlas.enums import StorageType
from atlas.math.timeseries import Timeseries


class StoragePO(StorageDispatchInput):
    storage_type: StorageType
    maximum_fcr: float
    maximum_afrr: float

    _cached_energy_forecast: Timeseries | None = None
    _cached_energy_forecat_initial: Timeseries | None = None

    def prefetch_forecasts(self, execution_date: DateTime, init_battery_time: DateTime):
        """
        Pre-fetch and cache forecasts for the entire optimization time window.

        :param execution_date: Execution date for forecasts
        :type execution_date: DateTime
        :param init_battery_time: Initial battery time
        :type init_battery_time: DateTime
        """
        if self.stored_energy:
            self._cached_energy_forecat_initial = self.stored_energy.get_forecast(
                execution_date, init_battery_time.subtract(days=2), init_battery_time
            )
            self._cached_energy_forecast = self.stored_energy.get_forecast(
                execution_date, init_battery_time, init_battery_time
            )
