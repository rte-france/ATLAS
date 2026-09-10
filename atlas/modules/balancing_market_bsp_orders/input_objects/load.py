"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BalancingLoad.
"""

from atlas.enums import LoadType
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.load import Load


class BalancingLoad(Load):
    """Load equipment subclass for the Balancing Orders Formulation module."""

    power: ForecastingMatrix | LazyForecastingMatrix
    variable_cost: AbstractTimeseries
    setup_delay: float
    maximum_gradient: float
    load_type: LoadType
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
