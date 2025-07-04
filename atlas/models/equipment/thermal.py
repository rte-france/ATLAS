"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from atlas.enum import ThermalStrategy
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Thermal(Equipment):
    """
    :param installed_capacity: Installed capacity
    :type installed_capacity: float
    :param minimum_stable_power_duration: Minimum stable power duration. Length of time that this unit must stay
    at a stable production level in between ramping periods
    :type minimum_stable_power_duration: float
    :param minimum_time_off: Minimum time that the unit must remain off after shutting down prior to a new start-up
    :type minimum_time_off: float
    :param minimum_time_on: Minimum time that the unit must remain on after starting up
    :type minimum_time_on: float
    :param outage_mean_duration: Sum of volume of sell offers on the Day Ahead market
    :type outage_mean_duration: float
    :param outage_probability: Probability of outage
    :type outage_probability: float
    :param scheduled_shutdown_mean_duration: Sum of volume of sell offers on the Day Ahead market
    :type scheduled_shutdown_mean_duration: float
    :param scheduled_shutdown_probability: Sum of volume of sell offers on the Day Ahead market
    :type scheduled_shutdown_probability: float
    :param shutdown_duration: Time it takes for the unit to shut down
    :type shutdown_duration: float
    :param startup_delay_probability: Sum of volume of sell offers on the Day Ahead market
    :type startup_delay_probability: float
    :param startup_duration: Time it takes for the unit to start up
    :type startup_duration: float
    :param strategy: Sum of volume of sell offers on the Day Ahead market
    :type strategy: ThermalStrategy
    :param state_sequence: Sum of volume of sell offers on the Day Ahead market
    :type state_sequence: ScenarioMatrix | LazyScenarioMatrix
    :param da_sell_submitted_volume: Sum of volume of sell offers on the Day Ahead market
    :type da_sell_submitted_volume: Timeseries
    :param maximum_power: Maximum power of the unit or cluster
    :type maximum_power: Timeseries
    :param minimum_power: Minimum power of the unit or cluster
    :type minimum_power: Timeseries
    :param co2_emission_factor: CO2 emissions per MWh
    :type co2_emission_factor: float
    """

    installed_capacity: float | None = Field(
        None,
        ge=0,
        description="Installed capacity (must be positive)",
    )
    minimum_stable_power_duration: float | None = Field(None, ge=0)
    minimum_time_off: float | None = Field(None, ge=0)
    minimum_time_on: float | None = Field(None, ge=0)
    outage_mean_duration: float | None = Field(None, ge=0)
    outage_probability: float | None = Field(None, ge=0, le=1)
    scheduled_shutdown_mean_duration: float | None = Field(None, ge=0)
    scheduled_shutdown_probability: float | None = Field(None, ge=0, le=1)
    shutdown_duration: float | None = Field(None, ge=0)
    startup_delay_probability: float | None = Field(None, ge=0, le=1)
    startup_duration: float | None = Field(None, ge=0)
    strategy: ThermalStrategy | None = None
    state_sequence: ScenarioMatrix | LazyScenarioMatrix | None = None
    da_sell_submitted_volume: Timeseries | LazyTimeseries | None = None
    maximum_power: Timeseries | LazyTimeseries | None = None
    minimum_power: Timeseries | LazyTimeseries | None = None

    @model_validator(mode="after")
    def validate_minimum_stable_power_duration(self) -> Thermal:
        """
        Validate that minimum_stable_power_duration is not greater than minimum_time_on.
        Raises ValidationError if the condition is violated.
        """
        if (
            self.minimum_stable_power_duration is not None
            and self.minimum_time_on is not None
            and self.minimum_stable_power_duration > self.minimum_time_on
        ):
            raise ValueError(
                f"MinimumStablePowerDuration ({self.minimum_stable_power_duration}) of equipment "
                f"{self.name} cannot be greater than MinimumTimeOn ({self.minimum_time_on})"
            )

        return self
