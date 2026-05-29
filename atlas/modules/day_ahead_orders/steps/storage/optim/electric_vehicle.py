"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.storage.optim.storage import StorageModel
from atlas.solver.models import SolverOptions


class ElectricVehicleModel(StorageModel):
    def __init__(
        self,
        parameters: DayAheadOrdersParameters,
        solver_name: str,
        name: str,
        storage: StorageDAO,
        solver_options: SolverOptions,
    ):
        """
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        :param solver_name: name of the solver
        :type solver_name: str
        :param name: name of the model
        :type name: str
        :param storage: storage object
        :type storage: StorageDAO
        :param solver_options: solver options
        :type solver_options: SolverOptions
        """
        super().__init__(parameters, solver_name, name, storage, storage.additional_hours, solver_options)

    def build_constraints(self) -> None:
        """Creation of constraints."""
        for t in self.time_frame:
            max_power = self.storage.maximum_power.get_value(t)
            min_power = self.storage.minimum_power.get_value(t)

            power_sell = self._dispatch.power_level_sell_var.get_value(t)
            power_buy = self._dispatch.power_level_buy_var.get_value(t)
            is_sell = self._dispatch.is_sell_var.get_value(t)

            self._dispatch.add_fragment_sum_constraints(t, power_sell, power_buy)

            self._dispatch.add_storage_level_evolution(self, t, self.parameters)

            # EV-specific sell/buy separation: V2G gates discharge
            self.add_constraint(
                power_sell <= self.storage.is_v2g * is_sell * max_power,
                f"Respect_Pmax_sale_at_{t}",
            )
            self.add_constraint(
                -power_buy <= (1 - is_sell * self.storage.is_v2g) * abs(min_power),
                f"Respect_Pmax_purchase_at_{t}",
            )

        assert self.storage.displacement_energy is not None, (
            f"displacement_energy is required for ElectricVehicle {self.storage.name}"
        )
        self.add_constraint(
            sum(-self._dispatch.power_level_buy_var.get_value(t) for t in self.time_frame)
            * self.storage.charge_efficiency
            >= (
                self.storage.displacement_energy.get_value(
                    self.parameters.temporal.end_date + self.optimization_period - self.parameters.temporal.timestep
                )
                - self.storage.displacement_energy.get_value(
                    self.parameters.temporal.start_date - self.parameters.temporal.timestep
                )
            )
            * self.parameters.ev_energy_coef,
            f"DisplacementEnergy_compensation_for_{str(self.storage.name)}",
        )
