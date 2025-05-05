"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import Field

from atlas.enum import ThermalStrategy
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Thermal(Equipment):
    """:param installed_capacity: Installed capacity
    :type installed_capacity: float
    :param minimum_stable_power_duration: Sum of volume of sell offers on the Day Ahead market
    :type minimum_stable_power_duration: float
    :param minimum_time_off: Equipment capping cost
    :type minimum_time_off: float
    :param minimum_time_on: Stores capping at the end of each Portfolio Optimization
    :type minimum_time_on: float
    :param outage_mean_duration: Sum of volume of sell offers on the Day Ahead market
    :type outage_mean_duration: float
    :param outage_probability: Sum of volume of sell offers on the Day Ahead market
    :type outage_probability: float
    :param scheduled_shutdown_mean_duration: Sum of volume of sell offers on the Day Ahead market
    :type scheduled_shutdown_mean_duration: float
    :param scheduled_shutdown_probability: Sum of volume of sell offers on the Day Ahead market
    :type scheduled_shutdown_probability: float
    :param shutdown_duration: Sum of volume of sell offers on the Day Ahead market
    :type shutdown_duration: float
    :param startup_delay_probability: Sum of volume of sell offers on the Day Ahead market
    :type startup_delay_probability: float
    :param startup_duration: Sum of volume of sell offers on the Day Ahead market
    :type startup_duration: float
    :param strategy: Sum of volume of sell offers on the Day Ahead market
    :type strategy: ThermalStrategy
    :param state_sequence: Sum of volume of sell offers on the Day Ahead market
    :type state_sequence: ScenarioMatrix | LazyScenarioMatrix
    :param da_sell_submitted_volume: Sum of volume of sell offers on the Day Ahead market
    :type da_sell_submitted_volume: Timeseries | LazyTimeseries
    :param maximum_power: Sum of volume of sell offers on the Day Ahead market
    :type maximum_power: Timeseries | LazyTimeseries
    :param minimum_power: Sum of volume of sell offers on the Day Ahead market
    :type minimum_power: Timeseries | LazyTimeseries
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
