"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.renewable import RenewableDispatch
from atlas.common.optimal_dispatch.reserves import RenewableReserveHandler, ReserveFactory
from atlas.common.optimal_dispatch.steps import AbstractOptimStep
from atlas.modules.portfolio_optimisation.input_objects.solar import SolarPO
from atlas.modules.portfolio_optimisation.input_objects.wind import WindPO
from atlas.modules.portfolio_optimisation.utils.getters import get_variable_cost
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class RenewableStep(AbstractOptimStep[WindPO | SolarPO, "PortfolioOptimisationParameters"]):
    """
    LP step shared by wind and solar units. Both equipment types have identical LP
    structure (power level bounded by a forecast, optional curtailment floor, standard
    reserve set), so a single step class handles them through the
    :class:`RenewableDispatch` and :class:`RenewableReserveHandler` building blocks.
    """

    _reserves: RenewableReserveHandler

    def __init__(self, equipment: WindPO | SolarPO):
        super().__init__(equipment)
        self._dispatch = RenewableDispatch(equipment)
        self._reserves = ReserveFactory.for_renewable(equipment)

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        self._dispatch.setup(model, parameters)
        self._reserves.setup(model)
        for time in parameters.equipment_time_window(eq):
            cfg.logger.debug(f"Adding variables for renewable unit {eq.name} at time {time}")
            self._dispatch.add_variables(time)
            self._reserves.add_variables(time, self._dispatch.max_power(time), self._dispatch.min_power(time))

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        for time in parameters.equipment_time_window(eq):
            cfg.logger.debug(f"Adding constraints for renewable unit {eq.name} at time {time}")
            self._dispatch.add_constraints(model, time)
            self._reserves.add_automated_capacity_constraints(time)
            self._reserves.add_capacity_constraints(time, self._dispatch.max_power(time))

    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict | None = None
    ):
        eq = self.equipment
        dt_h = parameters.temporal.timestep.total_hours()
        for time in parameters.equipment_time_window(eq):
            cfg.logger.debug(f"Adding objective for renewable unit {eq.name} at time {time}")
            power_level_var = self._dispatch.power_level_var.get_value(time)
            model.add_objective(get_variable_cost(eq, time) * power_level_var * dt_h)
