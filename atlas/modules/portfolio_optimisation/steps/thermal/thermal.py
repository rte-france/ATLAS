"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pendulum
from pendulum import Duration

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.steps.base import AbstractOptimStep
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class ThermalStep(AbstractOptimStep[ThermalPO]):
    """
    Step class owning all optimisation logic for ThermalPO.

    Composes :class:`ThermalDispatch` for physical variables and constraints;
    handles reserves, fill-up, and objective terms directly.
    """

    def __init__(self, equipment: ThermalPO):
        super().__init__(equipment)
        self._dispatch = ThermalDispatch(equipment)

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        self._dispatch.setup(model, parameters)

        eq = self.equipment
        for time in eq.optimisation_time_window:
            self._dispatch.add_variables(time)

            minimum_power = eq.minimum_power.get_value(time)
            maximum_power = eq.maximum_power.get_value(time)
            maximum_automated = get_maximum_automated(eq)

            add_reserve_variables(
                model=model,
                name=eq.name,
                time=time,
                min_power=minimum_power,
                max_power=maximum_power,
                maximum_automated=maximum_automated,
                relaxed_reserves=True,
                storage_equipment=False,
                thermal_equipment=True,
            )

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        d = self._dispatch
        ts = parameters.temporal.timestep

        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding constraints combination {d.combination} for {eq.name}")
            d.add_constraints(model, time, parameters)
            self._add_fill_up_constraints(model, time, parameters)
            self._add_reserve_constraints(model, time, parameters)

            if time in eq.optimisation_time_window[:-2]:
                d.add_dd_and_gradient_constraints(model, time, time - ts)

        self._add_daily_energy_constraint(model, ts)

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

    # ── PO-specific constraints ───────────────────────────────────────────

    def _add_fill_up_constraints(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> None:
        n = self.equipment.name
        eps = parameters.allowed_round_off_error
        p = self._dispatch.power_level_var.get_value(time)
        max_p = self.equipment.maximum_power.get_value(time)
        min_p = self.equipment.minimum_power.get_value(time)
        ru = model.get_variable(f"reserves_up_{n}_{time}")
        rd = model.get_variable(f"reserves_down_{n}_{time}")
        aru = model.get_variable(f"automated_reserves_up_{n}_{time}")
        ard = model.get_variable(f"automated_reserves_down_{n}_{time}")
        uru = model.get_variable(f"unprovided_reserves_up_{n}_{time}")
        urd = model.get_variable(f"unprovided_reserves_down_{n}_{time}")
        rr = model.get_variable(f"relaxed_reserves_{n}_{time}")

        model.add_constraint(p + ru + aru + uru <= max_p + eps, f"up_fillup_1_{time}_{n}")
        model.add_constraint(p + ru + aru + uru >= max_p - eps, f"up_fillup_2_{time}_{n}")
        model.add_constraint(p - rd - ard - urd + rr <= min_p + eps, f"down_fillup_1_{time}_{n}")
        model.add_constraint(p - rd - ard - urd + rr >= min_p - eps, f"down_fillup_2_{time}_{n}")

    def _add_reserve_constraints(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> None:
        n = self.equipment.name
        d = self._dispatch
        max_p = self.equipment.maximum_power.get_value(time)
        min_p = self.equipment.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self.equipment)
        off = d.off_var.get_value(time)
        ru = model.get_variable(f"reserves_up_{n}_{time}")
        rd = model.get_variable(f"reserves_down_{n}_{time}")
        aru = model.get_variable(f"automated_reserves_up_{n}_{time}")
        ard = model.get_variable(f"automated_reserves_down_{n}_{time}")
        rr = model.get_variable(f"relaxed_reserves_{n}_{time}")

        on_sum = d.on_up_var.get_value(time) + d.on_down_var.get_value(time)
        if d._has_flat:
            on_sum_flat = on_sum + d.on_flat_var.get_value(time)
        else:
            on_sum_flat = on_sum

        model.add_constraint(rr <= min_p * (1 - on_sum_flat), f"relaxed_reserves_{time}_{n}")

        unavail = off
        if d._has_start:
            unavail = unavail + d.on_start_var.get_value(time)
        if d._has_stop:
            unavail = unavail + d.stop_var.get_value(time)
        model.add_constraint(aru <= maximum_automated * (1 - unavail), f"automated_reserves_up_max_{time}_{n}")
        model.add_constraint(ard <= maximum_automated * (1 - unavail), f"automated_reserves_down_max_{time}_{n}")

        res_unavail = unavail
        if d._has_flat:
            res_unavail = res_unavail + on_sum
        model.add_constraint(ru <= max_p * (1 - res_unavail), f"reserves_up_max_{time}_{n}")
        model.add_constraint(rd <= max_p * (1 - res_unavail), f"reserves_down_max_{time}_{n}")

    def _add_daily_energy_constraint(self, model: OptimisationModel, timestep: Duration) -> None:
        eq = self.equipment
        if eq.has_daily_energy_constraint:
            days_in_optimes = sorted({pendulum.datetime(t.year, t.month, t.day) for t in eq.optimisation_time_window})
            for idx, date in enumerate(days_in_optimes):
                matching_steps = [
                    t
                    for t in eq.optimisation_time_window
                    if (t.year == date.year and t.month == date.month and t.day == date.day)
                ]
                if matching_steps and eq.maximum_daily_energy is not None:
                    constraint_expr = sum(
                        self._dispatch.power_level_var.get_value(t) for t in matching_steps
                    ) <= eq.maximum_daily_energy.get_value(date) * timestep.total_days() * len(matching_steps)
                    model.add_constraint(constraint_expr, f"energy_limit_day_{idx}_{eq.name}")
