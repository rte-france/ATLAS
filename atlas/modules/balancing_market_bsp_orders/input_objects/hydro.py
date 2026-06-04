"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BalancingHydro.
"""

from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.hydro import Hydro


class BalancingHydro(Hydro):
    """Hydro equipment subclass for the Balancing Orders Formulation module."""

    power: ForecastingMatrix | LazyForecastingMatrix
    fcr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    fcr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    afrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    afrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    mfrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    mfrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    rr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    rr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    variable_cost: AbstractTimeseries
    setup_delay: float
    maximum_gradient: float
    maximum_power: AbstractTimeseries
    minimum_power: AbstractTimeseries
    has_daily_energy_constraint: bool
    maximum_daily_energy: AbstractTimeseries
    minimum_daily_energy: AbstractTimeseries
    stored_energy: ForecastingMatrix | LazyForecastingMatrix
    storage_marginal_value: AbstractScenarioMatrix
    fragment_prices: list[float]
    fragment_volumes: list[float]
