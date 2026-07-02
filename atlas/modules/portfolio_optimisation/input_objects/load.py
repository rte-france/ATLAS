"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime

from atlas.common.optimal_dispatch.input_objects.load import LoadDispatchInput
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class LoadPO(LoadDispatchInput):
    _cached_forecast: Timeseries | None = None

    def prefetch_forecasts(self, execution_date: DateTime, parameters: PortfolioOptimisationParameters):
        """
        Pre-fetch and cache forecasts for the entire optimization time window.

        :param execution_date: Execution date for the forecast
        :type execution_date: DateTime
        :param parameters: Portfolio optimisation parameters, used to derive this equipment's time window
        :type parameters: PortfolioOptimisationParameters
        """
        window = parameters.equipment_time_window(self)
        if not window:
            return

        self._cached_forecast = self.maximum_power_forecast.get_forecast(execution_date, window[0], window[-1])
