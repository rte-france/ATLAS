"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime, Duration

from atlas.core.math.abstract_timeseries import AbstractTimeseries
from atlas.core.math.timeseries import Timeseries
from atlas.enums import StorageType
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.objects.equipment.storage import Storage


class StoragePO(Storage):
    storage_type: StorageType
    maximum_fcr: float
    maximum_afrr: float
    minimum_power: AbstractTimeseries
    maximum_power: AbstractTimeseries
    minimum_state_of_charge: AbstractTimeseries
    discharge_efficiency: float
    charge_efficiency: float
    maximum_energy: AbstractTimeseries
    additional_hours: Duration

    optimisation_time_window: list[DateTime] = []
    _cached_energy_forecast: Timeseries | None = None
    _cached_energy_forecat_initial: Timeseries | None = None

    def get_initial_stock(self, parameters: PortfolioOptimisationParameters) -> float:
        default_energy = (
            self.maximum_energy.get_value(parameters.temporal.start_date - parameters.temporal.timestep)
            * self.storage_initial_level
        )

        if self.stored_energy is None or not self._cached_energy_forecat_initial:
            return default_energy

        if self._cached_energy_forecast:
            return self._cached_energy_forecast.dataframe.select("time").head(1).item()

        return default_energy

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
