"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime, Duration

from atlas.core.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.core.math.abstract_timeseries import AbstractTimeseries
from atlas.core.math.timeseries import Timeseries
from atlas.objects.equipment.hydro import Hydro


class HydroPO(Hydro):
    maximum_energy: AbstractTimeseries
    minimum_energy: AbstractTimeseries
    maximum_fcr: float
    maximum_afrr: float
    minimum_power: AbstractTimeseries
    maximum_power: AbstractTimeseries
    initial_level: AbstractTimeseries
    storage_marginal_value: AbstractScenarioMatrix
    additional_hours: Duration

    optimisation_time_window: list[DateTime] = []
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
