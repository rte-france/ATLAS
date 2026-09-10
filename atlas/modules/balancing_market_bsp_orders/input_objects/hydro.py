"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BalancingHydro.
"""

from typing import Self

from pydantic import model_validator

from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.hydro import Hydro


class BalancingHydro(Hydro):
    """Hydro equipment subclass for the Balancing Orders Formulation module."""

    power: ForecastingMatrix | LazyForecastingMatrix
    setup_delay: float
    maximum_gradient: float
    maximum_power: AbstractTimeseries
    minimum_power: AbstractTimeseries
    has_daily_energy_constraint: bool
    stored_energy: ForecastingMatrix | LazyForecastingMatrix
    storage_marginal_value: AbstractScenarioMatrix
    fragment_prices: list[float]
    fragment_volumes: list[float]

    @model_validator(mode="after")
    def check_daily_energy_fields(self) -> Self:
        """
        Validate that maximum_daily_energy and minimum_daily_energy are provided
        when has_daily_energy_constraint is True.

        :raises ValueError: If has_daily_energy_constraint is True and either
            maximum_daily_energy or minimum_daily_energy is None
        :return: The validated BalancingHydro instance
        :rtype: BalancingHydro
        """
        if self.has_daily_energy_constraint:
            if self.maximum_daily_energy is None:
                raise ValueError("maximum_daily_energy must be provided when has_daily_energy_constraint is True")
            if self.minimum_daily_energy is None:
                raise ValueError("minimum_daily_energy must be provided when has_daily_energy_constraint is True")
        return self
