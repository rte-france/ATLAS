"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.storage.optim.storage import StorageModel
from atlas.solver.models import SolverOptions


class BatteryModel(StorageModel):
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

    def build_constraints(self, power_fragments: int) -> None:
        """
        Creation of constraints
        :param power_fragments: power fragments
        :type power_fragments: int
        :return: None
        """
        for t in self.time_frame:
            max_power = self.storage.maximum_power.get_value(t)
            min_power = self.storage.minimum_power.get_value(t)

            power_sell = self._dispatch.power_level_sell_var.get_value(t)
            power_buy = self._dispatch.power_level_buy_var.get_value(t)
            is_sell = self._dispatch.is_sell_var.get_value(t)

            # Fragment sum constraints — PO convention: sell_n >= 0, buy_n <= 0, direct sums
            self.add_constraint(
                power_sell == sum(self.get_variable(self.power_level_sell_n_key(t, i)) for i in range(power_fragments)),
                f"Evaluation_of_quantity_sold_at_{t}",
            )
            self.add_constraint(
                power_buy == sum(self.get_variable(self.power_level_buy_n_key(t, i)) for i in range(power_fragments)),
                f"Evaluation_of_quantity_purchased_at_{t}",
            )

            self._dispatch.add_storage_level_evolution(self, t, self.parameters)

            # Sell/buy separation: no efficiency factor (legacy-equivalent behaviour)
            self.add_constraint(power_sell <= is_sell * max_power, f"Respect_Pmax_sale_at_{t}")
            self.add_constraint(-power_buy <= (1 - is_sell) * abs(min_power), f"Respect_Pmax_purchase_at_{t}")

        self._dispatch.add_cycle_balance_constraint(self, self.time_frame)
