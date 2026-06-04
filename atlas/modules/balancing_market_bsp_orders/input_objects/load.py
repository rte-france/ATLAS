"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BalancingLoad.
"""

from atlas.enums import LoadType
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.modules.balancing_market_bsp_orders.input_objects.base import BalancingEquipmentMixin
from atlas.objects.equipment.load import Load


class BalancingLoad(BalancingEquipmentMixin, Load):
    """Load equipment subclass for the Balancing Orders Formulation module.

    Enforces attributes required by the load order formulator, in addition
    to the common balancing attributes defined in BalancingEquipmentMixin.
    """

    load_type: LoadType
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
