"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime, Duration

from atlas.common.optimal_dispatch.input_objects.hydro import HydroDispatchInput
from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.timeseries import Timeseries


class HydroPO(HydroDispatchInput):
    maximum_fcr: float
    maximum_afrr: float
    storage_marginal_value: AbstractScenarioMatrix

    _cached_energy_forecast: Timeseries | None = None

    def prefetch_forecasts(self, execution_date: DateTime, timestep: Duration, start_date: DateTime):
        """
        Pre-fetch and cache forecasts for the entire optimization time window.

        :param execution_date: Execution date for forecasts
        :type execution_date: DateTime
        :param timestep: Time step duration
        :type timestep: Duration
        :param start_date: Start date for optimization
        :type start_date: DateTime
        """
        if self.stored_energy:
            initial_time = start_date - timestep
            self._cached_energy_forecast = self.stored_energy.get_forecast(execution_date, initial_time, initial_time)
