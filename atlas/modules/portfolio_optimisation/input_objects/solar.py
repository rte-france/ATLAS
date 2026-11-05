"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.solar import Solar
from atlas.validators import DurationField


class SolarPO(Solar):
    maximum_fcr: float
    maximum_afrr: float
    maximum_curtailment_ratio: AbstractTimeseries
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    additional_hours: DurationField
