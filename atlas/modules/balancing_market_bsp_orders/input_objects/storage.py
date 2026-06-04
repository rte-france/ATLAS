"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BalancingStorage.
"""

from pendulum import Duration

from atlas.enums import StorageType
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.storage import Storage


class BalancingStorage(Storage):
    """Storage equipment subclass for the Balancing Orders Formulation module."""

    power: ForecastingMatrix | LazyForecastingMatrix
    fcr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    fcr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    afrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    afrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    mfrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    mfrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    rr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    rr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    variable_cost: AbstractTimeseries
    setup_delay: float
    maximum_gradient: float
    maximum_power: AbstractTimeseries
    minimum_power: AbstractTimeseries
    stored_energy: ForecastingMatrix | LazyForecastingMatrix
    maximum_energy: AbstractTimeseries
    charge_efficiency: float
    storage_type: StorageType
    transition_duration: Duration
