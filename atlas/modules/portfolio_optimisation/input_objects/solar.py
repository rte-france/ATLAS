"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime, Duration

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.objects.equipment.solar import Solar


class SolarPO(Solar):
    maximum_fcr: float
    maximum_afrr: float
    maximum_curtailment_ratio: AbstractTimeseries
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    additional_hours: Duration

    _cached_forecast: Timeseries | None = None

    def prefetch_forecasts(self, execution_date: DateTime, parameters: PortfolioOptimisationParameters):
        """Pre-fetch and cache forecasts for the entire optimization time window."""
        window = parameters.equipment_time_window(self)
        if not window:
            return

        self._cached_forecast = self.maximum_power_forecast.get_forecast(execution_date, window[0], window[-1])
