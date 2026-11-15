"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.validators import DurationField


class OtherNonDispatchablePO(OtherNonDispatchable):
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    additional_hours: DurationField
