"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
from atlas.common.optimal_dispatch.reserves import ReserveFactory, ThermalReserveHandler
from atlas.common.optimal_dispatch.steps import AbstractOptimStep
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class ThermalStep(AbstractOptimStep[ThermalPO]):
    """
    Step class owning all optimisation logic for ThermalPO.

    Composes :class:`ThermalDispatch` for physical variables and constraints and
    :class:`ThermalReserveFactory` for reserve variables and shared constraints;
    handles the PO objective terms directly.
    """

    _reserves: ThermalReserveHandler

    def __init__(self, equipment: ThermalPO):
        super().__init__(equipment)
        self._dispatch = ThermalDispatch(equipment)
        self._reserves = ReserveFactory.for_thermal(equipment, self._dispatch)

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        self._dispatch.setup(model, parameters)
        self._reserves.setup(model)

        eq = self.equipment
        for time in eq.optimisation_time_window:
            self._dispatch.add_variables(time)
            self._reserves.add_variables(
                time,
                eq.maximum_power.get_value(time),
                eq.minimum_power.get_value(time),
            )

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        d = self._dispatch
        ts = parameters.temporal.timestep

        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding constraints combination {d.combination} for {eq.name}")
            d.add_constraints(model, time, parameters)
            self._reserves.add_fill_up_constraints(
                time,
                d.power_level_var.get_value(time),
                eq.maximum_power.get_value(time),
                eq.minimum_power.get_value(time),
                parameters.allowed_round_off_error,
            )
            self._reserves.add_relaxed_reserve_constraint(time, eq.minimum_power.get_value(time))
            self._reserves.add_capacity_constraints(time, eq.maximum_power.get_value(time))

            if time in eq.optimisation_time_window[:-2]:
                d.add_dd_and_gradient_constraints(model, time, time - ts)

        self._dispatch.add_daily_energy_constraint(model, self.equipment.optimisation_time_window, ts)

    def add_objective(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
        price_forecasts: dict | None = None,
    ):
        if price_forecasts is None:
            price_forecasts = {}
        eq = self.equipment
        for time in eq.optimisation_time_window:
            price_forecast = price_forecasts.get(time, 0.0)
            variable_cost = eq.variable_cost.get_value(time)
            power_level_var = self._dispatch.power_level_var.get_value(time)
            model.add_objective(variable_cost * power_level_var * parameters.temporal.timestep.total_hours())

            if time > max(parameters.target_times):
                model.add_objective(-price_forecast * power_level_var * parameters.temporal.timestep.total_hours())

            if eq.startup_cost is not None:
                startup_cost = eq.startup_cost.get_value(time)
                turned_on_var = model.get_variable(f"t_on_{eq.name}_{time}")
                model.add_objective(startup_cost * turned_on_var)
