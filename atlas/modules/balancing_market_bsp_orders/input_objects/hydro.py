"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BalancingHydro.
"""

from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.modules.balancing_market_bsp_orders.input_objects.base import BalancingEquipmentMixin
from atlas.objects.equipment.hydro import Hydro


class BalancingHydro(BalancingEquipmentMixin, Hydro):
    """Hydro equipment subclass for the Balancing Orders Formulation module.

    Enforces attributes required by the hydraulic order formulator, in addition
    to the common balancing attributes defined in BalancingEquipmentMixin.
    """

    maximum_power: AbstractTimeseries
    minimum_power: AbstractTimeseries
    has_daily_energy_constraint: bool
    stored_energy: ForecastingMatrix | LazyForecastingMatrix
    storage_marginal_value: AbstractScenarioMatrix
    fragment_prices: list[float]
    fragment_volumes: list[float]
