"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.solar import Solar


class SolarIDO(Solar):
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    maximum_curtailment_ratio: AbstractTimeseries
    variable_cost: AbstractTimeseries
    da_cleared_quantity: AbstractTimeseries
