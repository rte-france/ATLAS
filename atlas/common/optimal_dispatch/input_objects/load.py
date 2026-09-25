"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from atlas.enums import LoadType
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.load import Load
from atlas.validators import DurationField


class LoadDispatchInput(Load):
    """
    Physical contract for load dispatch — fields read by :class:`LoadDispatch`.

    :param load_type: Load type (e.g. power-to-gas, standard).
    :param maximum_power_forecast: Forecast of maximum consumption power.
    :param additional_hours: Extra hours appended to the optimisation window.
    """

    load_type: LoadType
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    additional_hours: DurationField
