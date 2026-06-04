"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BalancingThermal.
"""

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.modules.balancing_market_bsp_orders.input_objects.base import BalancingEquipmentMixin
from atlas.objects.equipment.thermal import Thermal


class BalancingThermal(BalancingEquipmentMixin, Thermal):
    """Thermal equipment subclass for the Balancing Orders Formulation module.

    Enforces attributes required by the thermal order formulator, in addition
    to the common balancing attributes defined in BalancingEquipmentMixin.
    """

    maximum_power: AbstractTimeseries
    minimum_power: AbstractTimeseries
