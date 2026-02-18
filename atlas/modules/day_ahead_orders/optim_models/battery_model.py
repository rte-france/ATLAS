"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum.duration import Duration

from atlas import SolverOptions
from atlas.modules.day_ahead_orders.data_models.storage import StorageDAO
from atlas.modules.day_ahead_orders.optim_models.storage_model import StorageModel
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters


class BatteryModel(StorageModel):
    def __init__(
        self,
        parameters: DayAheadOrdersParameters,
        solver_name: str,
        name: str,
        storage: StorageDAO,
        optimization_period: Duration,
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
        :param optimization_period: duration of the optimization
        :type optimization_period: Duration
        :param solver_options: solver options
        :type solver_options: SolverOptions
        """
        super().__init__(parameters, solver_name, name, storage, optimization_period, solver_options)

    def create_constraints(self, initial_stock: float | None, power_fragments: int) -> None:
        """
        Creation of constraints
        :param initial_stock: initial stock
        :type initial_stock: float | None
        :param power_fragments: power fragments
        :type power_fragments: int
        :return: None
        """
        for t in self.time_frame:
            for i in range(power_fragments):
                self.add_constraint(
                    self.get_variable(StorageModel.amount_sold_in_fragment_at_key(t, i)) * power_fragments
                    <= self.storage.maximum_power.get_value(t),
                    f"Respect_of_sale_power_fragment_{i}_limit_at_{t}",
                )
                self.add_constraint(
                    self.get_variable(StorageModel.amount_purchased_in_fragment_at_key(t, i)) * power_fragments
                    <= abs(self.storage.minimum_power.get_value(t)),
                    f"Respect_of_purchase_power_fragment_{i}_limit_at_{t}",
                )

            # Total bought/sold energy at each time step is the sum of the fragments at time step
            self.add_constraint(
                self.get_variable(StorageModel.sold_at_key(t))
                == sum(
                    self.get_variable(StorageModel.amount_sold_in_fragment_at_key(t, i)) for i in range(power_fragments)
                ),
                f"Evaluation_of_quantity_sold_at_{t}",
            )
            self.add_constraint(
                self.get_variable(StorageModel.purchased_at_key(t))
                == sum(
                    self.get_variable(StorageModel.amount_purchased_in_fragment_at_key(t, i))
                    for i in range(power_fragments)
                ),
                f"Evaluation_of_quantity_purchased_at_{t}",
            )

            # StoredEnergy tracking constraint, evaluates the stock at each time step
            if t == self.parameters.start_date:
                self.add_constraint(
                    self.get_variable(StorageModel.stored_energy_at_key(t))
                    == (
                        initial_stock
                        + self.parameters.timestep.total_hours()
                        * (
                            self.get_variable(StorageModel.purchased_at_key(t)) * self.storage.charge_efficiency
                            - self.get_variable(StorageModel.sold_at_key(t)) / self.storage.discharge_efficiency
                        )
                    ),
                    f"Stock_tracking_at_{t + self.parameters.timestep}",
                )
            else:
                self.add_constraint(
                    self.get_variable(StorageModel.stored_energy_at_key(t))
                    == self.get_variable(StorageModel.stored_energy_at_key(t - self.parameters.timestep))
                    + self.parameters.timestep.total_hours()
                    * (
                        self.get_variable(StorageModel.purchased_at_key(t)) * self.storage.charge_efficiency
                        - self.get_variable(StorageModel.sold_at_key(t)) / self.storage.discharge_efficiency
                    ),
                    f"Stock_tracking_at_{t + self.parameters.timestep}",
                )

            # Respect of system states constraints (isSell and isV2G)
            self.add_constraint(
                self.get_variable(StorageModel.sold_at_key(t))
                <= self.get_variable(StorageModel.is_sell_at_key(t)) * self.storage.maximum_power.get_value(t),
                f"Respect_Pmax_sale_at_{t}",
            )
            self.add_constraint(
                self.get_variable(StorageModel.purchased_at_key(t))
                <= (1 - self.get_variable(StorageModel.is_sell_at_key(t)))
                * abs(self.storage.minimum_power.get_value(t)),
                f"Respect_Pmax_purchase_at_{t}",
            )
            self.add_constraint(self.get_variable(StorageModel.sold_at_key(t)) >= 0, f"Respect_Pmin_sale_at_{t}")
            self.add_constraint(
                self.get_variable(StorageModel.purchased_at_key(t)) >= 0, f"Respect_Pmin_purchase_at_{t}"
            )

            # Respect of minimum and maximum storage levels constraints
            self.add_constraint(
                self.get_variable(StorageModel.stored_energy_at_key(t))
                >= (self.storage.minimum_state_of_charge.get_value(t) * self.storage.maximum_energy.get_value(t)),
                f"Minimum_storage_level_constraint_at_{t}",
            )
            self.add_constraint(
                self.get_variable(StorageModel.stored_energy_at_key(t)) <= self.storage.maximum_energy.get_value(t),
                f"Maximum_storage_level_constraint_at_{t}",
            )

        # Respect of the balance between sales and purchases
        self.add_constraint(
            sum(self.get_variable(StorageModel.purchased_at_key(t)) for t in self.time_frame)
            * self.storage.charge_efficiency
            == sum(self.get_variable(StorageModel.sold_at_key(t)) for t in self.time_frame)
            / self.storage.discharge_efficiency,
            "Respect_of_cycle_balance",
        )
