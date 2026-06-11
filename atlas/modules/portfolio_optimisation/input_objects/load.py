"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime, Duration

from atlas.enums import LoadType
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.objects.equipment.load import Load


class LoadPO(Load):
    load_type: LoadType
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    additional_hours: Duration

    optimisation_time_window: list[DateTime] = []
    _cached_forecast: Timeseries | None = None

    def prefetch_forecasts(self, execution_date: DateTime):
        """
        Pre-fetch and cache forecasts for the entire optimization time window.

        :param execution_date: Execution date for the forecast
        :type execution_date: DateTime
        """
        if not self.optimisation_time_window:
            return

        start_time = self.optimisation_time_window[0]
        end_time = self.optimisation_time_window[-1]

        self._cached_forecast = self.maximum_power_forecast.get_forecast(execution_date, start_time, end_time)
