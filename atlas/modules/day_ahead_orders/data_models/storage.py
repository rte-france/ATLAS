"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import LazyTimeseries, Storage, Timeseries
from atlas.modules.day_ahead_orders.data_models.portfolio import PortfolioDAO


class StorageDAO(Storage):
    portfolio: PortfolioDAO
    maximum_energy: Timeseries | LazyTimeseries
    minimum_power: Timeseries | LazyTimeseries
    maximum_power: Timeseries | LazyTimeseries
    variable_cost: Timeseries
    displacement_energy: Timeseries | LazyTimeseries
    storage_initial_level: float
    minimum_state_of_charge: Timeseries | LazyTimeseries
