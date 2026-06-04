"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BalancingStorage.
"""

from pendulum import Duration

from atlas.enums import StorageType
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.modules.balancing_market_bsp_orders.input_objects.base import BalancingEquipmentMixin
from atlas.objects.equipment.storage import Storage


class BalancingStorage(BalancingEquipmentMixin, Storage):
    """Storage equipment subclass for the Balancing Orders Formulation module.

    Enforces attributes required by the storage order formulator, in addition
    to the common balancing attributes defined in BalancingEquipmentMixin.
    """

    maximum_power: AbstractTimeseries
    minimum_power: AbstractTimeseries
    stored_energy: ForecastingMatrix | LazyForecastingMatrix
    maximum_energy: AbstractTimeseries
    charge_efficiency: float
    storage_type: StorageType
    transition_duration: Duration
