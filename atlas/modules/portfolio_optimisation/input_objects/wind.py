"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime, Duration

from atlas.core.math.abstract_timeseries import AbstractTimeseries
from atlas.core.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.core.math.timeseries import Timeseries
from atlas.objects.equipment.wind import Wind


class WindPO(Wind):
    maximum_fcr: float
    maximum_afrr: float
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    maximum_curtailment_ratio: AbstractTimeseries
    additional_hours: Duration

    optimisation_time_window: list[DateTime] = []
    _cached_forecast: Timeseries | None = None

    def prefetch_forecasts(self, execution_date: DateTime):
        """Pre-fetch and cache forecasts for the entire optimization time window."""
        if not self.optimisation_time_window:
            return

        start_time = self.optimisation_time_window[0]
        end_time = self.optimisation_time_window[-1]

        self._cached_forecast = self.maximum_power_forecast.get_forecast(execution_date, start_time, end_time)
