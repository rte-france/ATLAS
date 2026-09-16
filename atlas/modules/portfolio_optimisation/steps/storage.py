"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.storage import StorageDispatch
from atlas.common.optimal_dispatch.reserves import ReserveFactory, StorageReserveHandler
from atlas.common.optimal_dispatch.steps import AbstractOptimStep
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class StoragePOStep(AbstractOptimStep[StoragePO, "PortfolioOptimisationParameters"]):
    """
    Step class owning all optimisation logic for StoragePO.

    Composes :class:`StorageDispatch` for physical variables and constraints and
    :class:`StorageReserveHandler` for reserve variables and constraints;
    handles fragment and cycle-balance logic directly.
    """

    _reserves: StorageReserveHandler

    def __init__(self, equipment: StoragePO):
        super().__init__(equipment)
        self._dispatch = StorageDispatch(equipment)
        self._reserves = ReserveFactory.for_storage(equipment)

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        nbr_fragment: int = parameters.storage_mapping[eq.storage_type]["nb_fragment"]

        self._dispatch.setup(model, parameters, nbr_fragment)
        self._reserves.setup(model)

        for time in parameters.equipment_time_window(eq):
            cfg.logger.debug(f"Adding variables for storage unit {eq.name} at time {time}")
            max_power = eq.maximum_power.get_value(time)
            min_power = eq.minimum_power.get_value(time)

            self._dispatch.add_variables(time)
            self._reserves.add_variables(time, max_power, min_power)
            self._dispatch.add_fragment_variables(time, max_power, min_power)

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        if eq.maximum_energy.max() <= 0:
            cfg.logger.debug(f"Skipping constraints for storage unit {eq.name} - maximum energy is 0")
            return

        window = parameters.equipment_time_window(eq)
        for time in window:
            cfg.logger.debug(f"Adding constraints for storage unit {eq.name} at time {time}")

            max_power = eq.maximum_power.get_value(time)
            max_energy = eq.maximum_energy.get_value(time)
            min_soc = eq.minimum_state_of_charge.get_value(time)

            self._dispatch.add_constraints(model, time, parameters)
            self._reserves.add_bound_constraints(time, max_power)

            self._reserves.add_fill_up_constraints(
                time,
                self._dispatch.power_level_sell_var.get_value(time),
                self._dispatch.power_level_buy_var.get_value(time),
                self._dispatch.effective_max_sell(time),
                self._dispatch.effective_min_buy(time),
            )
            self._reserves.add_capacity_constraints(
                time,
                self._dispatch.stored_energy_var.get_value(time),
                max_energy,
                min_soc,
                parameters.battery_reserve_duration.total_hours(),
                parameters.battery_automated_reserve_duration.total_hours(),
            )

            if time not in parameters.portfolio_time_window:
                self._dispatch.add_fragment_sum_constraints(
                    time,
                    self._dispatch.power_level_sell_var.get_value(time),
                    self._dispatch.power_level_buy_var.get_value(time),
                )

        self._dispatch.add_cycle_balance_constraint(model, window, parameters)

    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict | None = None
    ):
        if price_forecasts is None:
            price_forecasts = {}
        eq = self.equipment
        if eq.maximum_energy.max() <= 0:
            cfg.logger.debug(f"Skipping objective for storage unit {eq.name} - maximum energy is 0")
            return

        for time in parameters.equipment_time_window(eq):
            cfg.logger.debug(f"Adding objective for storage unit {eq.name} at time {time}")
            price_forecast = price_forecasts.get(time, 0.0)
            power_level_sell_var = self._dispatch.power_level_sell_var.get_value(time)
            power_level_buy_var = self._dispatch.power_level_buy_var.get_value(time)
            model.add_objective(
                -price_forecast
                * (power_level_buy_var + power_level_sell_var)
                * parameters.temporal.timestep.total_hours()
            )

            if time not in parameters.portfolio_time_window:
                smoothing_factor = parameters.storage_mapping[eq.storage_type]["smoothing_factor"]
                nb_fragment = parameters.storage_mapping[eq.storage_type]["nb_fragment"]

                for n in range(nb_fragment):
                    sell_n = self._dispatch.get_fragment_sell_var(time, n)
                    buy_n = self._dispatch.get_fragment_buy_var(time, n)

                    if nb_fragment == 1 and n == 0:
                        model.add_objective(-(sell_n + buy_n) * price_forecast)
                    else:
                        model.add_objective(
                            -sell_n * price_forecast * (1 - n * smoothing_factor / (nb_fragment - 1))
                            - buy_n * price_forecast * (1 + n * smoothing_factor / (nb_fragment - 1))
                        )
