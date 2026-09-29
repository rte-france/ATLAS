"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.hydro import HydroDispatch
from atlas.common.optimal_dispatch.marginal_pricing import InterpolatedMarginalValue
from atlas.common.optimal_dispatch.reserves import HydroReserveHandler, ReserveFactory
from atlas.common.optimal_dispatch.steps import AbstractOptimStep
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class HydroStep(AbstractOptimStep[HydroPO, "PortfolioOptimisationParameters"]):
    """
    LP step for a hydro reservoir unit. Composes :class:`HydroDispatch` (stored energy +
    fragments + balance) and :class:`HydroReserveHandler` (reserves + storage-level
    coupling). The PO-specific marginal-value pricing is kept here as it is a property of
    the objective, not the physical dispatch.
    """

    _reserves: HydroReserveHandler

    def __init__(self, equipment: HydroPO):
        super().__init__(equipment)
        self._dispatch = HydroDispatch(equipment)
        self._reserves = ReserveFactory.for_hydro(equipment, self._dispatch)

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        self._dispatch.setup(model, parameters)
        self._reserves.setup(model)
        cfg.logger.debug(f"Adding variables for hydro unit {eq.name}")
        window = parameters.equipment_time_window(eq)
        self._dispatch.add_variables(window)
        self._reserves.add_variables(window, eq.maximum_power, eq.minimum_power)

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        for time in parameters.equipment_time_window(eq):
            cfg.logger.debug(f"Adding constraints for hydro unit {eq.name} at time {time}")
            min_power = eq.minimum_power.get_value(time)
            max_power = eq.maximum_power.get_value(time)

            self._reserves.add_relaxed_reserve_constraint(time, min_power)
            self._reserves.add_automated_capacity_constraints(time)
            self._reserves.add_capacity_constraints(time, max_power)

            if time in parameters.portfolio_time_window:
                self._dispatch.add_energy_balance(model, time, parameters)
                self._reserves.add_storage_level_constraints(
                    time, eq.minimum_energy.get_value(time), eq.maximum_energy.get_value(time)
                )

    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict | None = None
    ):
        if price_forecasts is None:
            price_forecasts = {}
        eq = self.equipment
        dt_h = parameters.temporal.timestep.total_hours()
        marginal_value = InterpolatedMarginalValue.for_unit(
            eq,
            parameters.temporal.execution_date,
            parameters.temporal.start_date - parameters.temporal.timestep,
        )

        for time in parameters.equipment_time_window(eq):
            cfg.logger.debug(f"Adding objective for hydro unit {eq.name} at time {time}")
            price_forecast = price_forecasts.get(time, 0.0)

            for k in self._dispatch.fragment_volumes(time):
                fragment_price = eq.fragment_data[k].price + marginal_value.value_at(time)
                power_level_frag_var = self._dispatch.power_level_frag[k][time]

                if time in parameters.portfolio_time_window:
                    model.add_objective(fragment_price * power_level_frag_var * dt_h)
                else:
                    model.add_objective(-(price_forecast - fragment_price) * power_level_frag_var * dt_h)
            cfg.logger.debug(f"Finished adding objective for hydro unit {eq.name} at time {time}")
