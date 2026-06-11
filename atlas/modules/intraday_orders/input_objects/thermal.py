"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.enums import ThermalStrategy
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.thermal import Thermal


class ThermalIDO(Thermal):
    strategy: ThermalStrategy
    da_cleared_quantity: AbstractTimeseries
    total_id_cleared_quantity: AbstractTimeseries
    id_po_for_orders: ForecastingMatrix | LazyForecastingMatrix
    minimum_power: AbstractTimeseries
    maximum_power: AbstractTimeseries
    startup_cost: AbstractTimeseries
    variable_cost: AbstractTimeseries
    id_buy_submitted_volume: ForecastingMatrix | LazyForecastingMatrix
    id_sell_submitted_volume: ForecastingMatrix | LazyForecastingMatrix
    total_id_buy_submitted_volume: AbstractTimeseries
    total_id_sell_submitted_volume: AbstractTimeseries
