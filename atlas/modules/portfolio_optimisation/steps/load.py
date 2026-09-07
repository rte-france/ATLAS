"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.load import LoadDispatch
from atlas.common.optimal_dispatch.steps import AbstractOptimStep
from atlas.enums import LoadType
from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
from atlas.modules.portfolio_optimisation.utils.getters import get_variable_cost
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class LoadStep(AbstractOptimStep[LoadPO, "PortfolioOptimisationParameters"]):
    """
    LP step for a load unit. Composes :class:`LoadDispatch` for the consumption variable
    and bounds. The PO objective adds the consumption cost (or the gas-market spread for
    Power-to-Gas units, which behave as price-responsive loads).
    """

    def __init__(self, equipment: LoadPO):
        super().__init__(equipment)
        self._dispatch = LoadDispatch(equipment)

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        self._dispatch.setup(model, parameters)
        for time in parameters.equipment_time_window(eq):
            cfg.logger.debug(f"Adding variables for load unit {eq.name} at time {time}")
            self._dispatch.add_variables(time)

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        for time in parameters.equipment_time_window(eq):
            cfg.logger.debug(f"Adding constraints for load unit {eq.name} at time {time}")
            self._dispatch.add_constraints(model, time)

    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict | None = None
    ):
        if price_forecasts is None:
            price_forecasts = {}
        eq = self.equipment
        dt_h = parameters.temporal.timestep.total_hours()
        for time in parameters.equipment_time_window(eq):
            cfg.logger.debug(f"Adding objective for load unit {eq.name} at time {time}")
            price_forecast = price_forecasts.get(time, 0.0)
            power_level_var = self._dispatch.power_level_var.get_value(time)
            if eq.load_type == LoadType.POWER_TO_GAS:
                model.add_objective((get_variable_cost(eq, time) - price_forecast) * power_level_var * dt_h)
            else:
                model.add_objective(get_variable_cost(eq, time) * -power_level_var * dt_h)
