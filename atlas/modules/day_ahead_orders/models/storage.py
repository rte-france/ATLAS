"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic_extra_types.pendulum_dt import Duration

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.models.equipment.storage import Storage
from atlas.modules.day_ahead_orders.models.portfolio import PortfolioDAO


class StorageDAO(Storage):
    portfolio: PortfolioDAO
    maximum_energy: AbstractTimeseries
    minimum_power: AbstractTimeseries
    maximum_power: AbstractTimeseries
    variable_cost: AbstractTimeseries
    displacement_energy: AbstractTimeseries
    storage_initial_level: float
    minimum_state_of_charge: AbstractTimeseries
    additional_hours: Duration
