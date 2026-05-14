"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.enums import LoadType
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.load import Load


class LoadIDO(Load):
    load_type: LoadType
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    variable_cost: AbstractTimeseries
    da_cleared_quantity: AbstractTimeseries
    total_id_cleared_quantity: AbstractTimeseries
    id_buy_submitted_volume: ForecastingMatrix | LazyForecastingMatrix
    id_sell_submitted_volume: ForecastingMatrix | LazyForecastingMatrix
    total_id_buy_submitted_volume: AbstractTimeseries
    total_id_sell_submitted_volume: AbstractTimeseries
