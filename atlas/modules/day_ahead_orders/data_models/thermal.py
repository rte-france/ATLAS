"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import Duration

from atlas import LazyTimeseries, Thermal, Timeseries
from atlas.modules.day_ahead_orders.data_models.portfolio import PortfolioDAO


class ThermalDAO(Thermal):
    portfolio: PortfolioDAO
    variable_cost: Timeseries | LazyTimeseries
    startup_cost: Timeseries | LazyTimeseries
    minimum_time_on: Duration
    maximum_power: Timeseries | LazyTimeseries
    minimum_power: Timeseries | LazyTimeseries
    minimum_stable_power_duration: Duration
    maximum_daily_energy: Timeseries | LazyTimeseries
    minimum_time_off: Duration
