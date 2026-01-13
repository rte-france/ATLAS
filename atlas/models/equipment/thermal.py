"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_extra_types.pendulum_dt import Duration

from atlas.enum import ThermalStrategy
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment
from atlas.validators import convert_to_duration


class Thermal(Equipment):
    """
    :param installed_capacity: Installed capacity
    :type installed_capacity: float
    :param minimum_stable_power_duration: Minimum stable power duration. Length of time that this unit must stay
    at a stable production level in between ramping periods. Provide as float (hours) or Duration object.
    :type minimum_stable_power_duration: Duration | float
    :param minimum_time_off: Minimum time that the unit must remain off after shutting down prior to a new start-up.
    Provide as float (hours) or Duration object.
    :type minimum_time_off: Duration | float
    :param minimum_time_on: Minimum time that the unit must remain on after starting up.
    Provide as float (hours) or Duration object.
    :type minimum_time_on: Duration | float
    :param outage_mean_duration: Mean duration of an outage, in hours.
    :type outage_mean_duration: Duration | float
    :param outage_probability: Probability of outage
    :type outage_probability: float
    :param scheduled_shutdown_mean_duration: Mean duration of a scheduled shutdown, in hours.
    :type scheduled_shutdown_mean_duration: float
    :param scheduled_shutdown_probability: Probability of a scheduled shutdown
    :type scheduled_shutdown_probability: float
    :param shutdown_duration: Time it takes for the unit to shut down.
    Provide as float (hours) or Duration object.
    :type shutdown_duration: Duration | float
    :param startup_delay_probability: Probability of a startup delay, which is the time it takes
    :type startup_delay_probability: float
    :param startup_duration: Time it takes for the unit to start up.
    Provide as float (hours) or Duration object.
    :type startup_duration: Duration | float
    :param strategy: Thermal strategy to be used for this unit. Possible values are "thermal", "thermal_with_startup_delay", "thermal_with_shutdown".
    :type strategy: ThermalStrategy
    :param state_sequence: Sequence of states for the thermal unit.
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
    minimum_stable_power_duration: Duration | None = Field(
        None, description="Minimum stable power duration in hours (will be converted to Duration)"
    )
    minimum_time_off: Duration | None = Field(
        None, description="Minimum time off in hours (will be converted to Duration)"
    )
    minimum_time_on: Duration | None = Field(
        None, description="Minimum time on in hours (will be converted to Duration)"
    )
    outage_mean_duration: Duration | None = Field(None)
    outage_probability: float | None = Field(None, ge=0, le=1)
    scheduled_shutdown_mean_duration: float | None = Field(None)
    scheduled_shutdown_probability: float | None = Field(None, ge=0, le=1)
    shutdown_duration: Duration | None = Field(
        None, description="Shutdown duration in hours (will be converted to Duration)"
    )
    startup_delay_probability: float | None = Field(None, ge=0, le=1)
    startup_duration: Duration | None = Field(
        None, description="Startup duration in hours (will be converted to Duration)"
    )
    strategy: ThermalStrategy | None = None
    state_sequence: ScenarioMatrix | LazyScenarioMatrix | None = None
    da_sell_submitted_volume: Timeseries | LazyTimeseries | None = None
    maximum_power: Timeseries | LazyTimeseries | None = None
    minimum_power: Timeseries | LazyTimeseries | None = None

    @field_validator(
        "minimum_stable_power_duration",
        "minimum_time_off",
        "minimum_time_on",
        "outage_mean_duration",
        "shutdown_duration",
        "startup_duration",
        mode="before",
    )
    @classmethod
    def parse_duration(cls, v):
        """Convert various duration formats to Duration objects."""
        return convert_to_duration(v)
