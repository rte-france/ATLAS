"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BalancingWind.
"""

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.modules.balancing_market_bsp_orders.input_objects.base import BalancingEquipmentMixin
from atlas.objects.equipment.wind import Wind


class BalancingWind(BalancingEquipmentMixin, Wind):
    """Wind equipment subclass for the Balancing Orders Formulation module.

    Enforces attributes required by the wind/PV order formulator, in addition
    to the common balancing attributes defined in BalancingEquipmentMixin.
    """

    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    maximum_curtailment_ratio: AbstractTimeseries
