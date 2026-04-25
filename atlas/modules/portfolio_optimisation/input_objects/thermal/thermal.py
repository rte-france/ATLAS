"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import math

from pendulum import DateTime
from pydantic import model_validator

import atlas.config as cfg
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.objects.equipment.thermal import Thermal


class ThermalPO(Thermal):
    """
    Thermal power equipment data model for portfolio optimisation.
    """

    maximum_fcr: float
    maximum_afrr: float
    maximum_power: AbstractTimeseries
    variable_cost: AbstractTimeseries
    maximum_gradient: float = 0.0
    has_daily_energy_constraint: bool = False

    _T_on: int = 0
    _T_off: int = 0
    _T_start: int = 0
    _T_stop: int = 0
    _T_stable: int = 0
    _Delta_Q: float = 0.0
    _Delta_Q_unconstrained: float = 0.0
    _combination: int = 1
    T_traceback: int = 0
    optimisation_time_window: list[DateTime] = []

    def _compute_time_parameters(self, parameters: PortfolioOptimisationParameters):
        """
        Compute time step parameters from duration constraints.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        """
        if self.minimum_time_on and self.minimum_time_on.total_minutes() > 0:
            self._T_on = int(max(1, math.ceil(self.minimum_time_on / parameters.temporal.timestep))) + 1
        else:
            self._T_on = 0

        if self.minimum_time_off and self.minimum_time_off.total_minutes() > 0:
            self._T_off = int(max(1, math.ceil(self.minimum_time_off / parameters.temporal.timestep))) + 1
        else:
            self._T_off = 0

        if self.startup_duration:
            self._T_start = int(math.floor(self.startup_duration / parameters.temporal.timestep))
        else:
            self._T_start = 0

        if self.shutdown_duration:
            self._T_stop = int(math.floor(self.shutdown_duration / parameters.temporal.timestep))
        else:
            self._T_stop = 0

        if self.minimum_stable_power_duration:
            if self.minimum_stable_power_duration < parameters.temporal.timestep:
                self._T_stable = 0
            else:
                self._T_stable = int(math.ceil(self.minimum_stable_power_duration / parameters.temporal.timestep)) + 1
                self._T_stable = self._T_stable if self._T_stable >= 2 else 0
        else:
            self._T_stable = 0

        self._Delta_Q = self.maximum_gradient * parameters.temporal.timestep.total_minutes()
        self._Delta_Q_unconstrained = self.maximum_power.slice(
            parameters.temporal.start_date, parameters.temporal.end_date, inplace=False
        ).max()

        self._combination = self._determine_combination()

    def _determine_combination(self) -> int:
        """
        Determine which of the 8 constraint combinations to use.

        :return: Combination number (1-8)
        :rtype: int
        """
        if self._T_stop == 0 and self._T_start == 0 and self._T_stable == 0:
            return 1
        elif self._T_stop >= 1 and self._T_start == 0 and self._T_stable == 0:
            return 2
        elif self._T_stop == 0 and self._T_start == 0 and self._T_stable >= 1:
            return 3
        elif self._T_start >= 1 and self._T_stop == 0 and self._T_stable == 0:
            return 4
        elif self._T_stop >= 1 and self._T_start == 0 and self._T_stable >= 1:
            return 5
        elif self._T_stop == 0 and self._T_start >= 1 and self._T_stable >= 1:
            return 6
        elif self._T_stop >= 1 and self._T_start >= 1 and self._T_stable == 0:
            return 7
        elif self._T_stop >= 1 and self._T_start >= 1 and self._T_stable >= 1:
            return 8
        else:
            cfg.logger("Combination constraint set can not be determined, default to 1.")
            return 1

    @model_validator(mode="after")
    def validate_minimum_stable_power_duration(self) -> ThermalPO:
        """
        Validate that minimum_stable_power_duration is not greater than minimum_time_on.
        """
        if (
            self.minimum_stable_power_duration is not None
            and self.minimum_time_on is not None
            and self.minimum_stable_power_duration > self.minimum_time_on
        ):
            raise ValueError(
                f"minimum_stable_power_duration ({self.minimum_stable_power_duration.total_hours()}h) of equipment "
                f"{self.name} cannot be greater than minimum_time_on ({self.minimum_time_on.total_hours()}h)"
            )
        return self
