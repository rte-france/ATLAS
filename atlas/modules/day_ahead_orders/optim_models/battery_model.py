"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic_extra_types.pendulum_dt import DateTime

from atlas import Equipment
from atlas.modules.day_ahead_orders.optim_models.dao_base_model import DAOBaseModel


class BatteryModel(DAOBaseModel):
    def __init__(
        self,
        solver_name: str,
        name: str,
        start_date: DateTime,
        end_date: DateTime,
        execution_date: DateTime,
        time_step: int,
        equipment: Equipment,
        optimization_period: int,
    ):
        super().__init__(
            solver_name, name, start_date, end_date, execution_date, time_step, equipment, optimization_period
        )

    def create_constraints(self, initial_stock: float | None, power_fragments: int):
        """
        Creation of constraints
        :param initial_stock: initial stock
        :param power_fragments: power fragments
        :return: None
        """
        for t in self.time_frame:
            for i in range(power_fragments):
                self.add_constraint(
                    self.Qvf[t][i] * power_fragments <= self.equipment.maximum_power.get_value(t),
                    "Respect_of_sale_power_fragment_{}_limit_at_{}".format(i, t),
                )
                self.add_constraint(
                    self.Qaf[t][i] * power_fragments <= abs(self.equipment.minimum_power.get_value(t)),
                    "Respect_of_purchase_power_fragment_{}_limit_at_{}".format(i, t),
                )

            # Total bought/sold energy at each time step is the sum of the fragments at time step
            self.add_constraint(
                self.Qv[t] == sum(self.Qvf[t][i] for i in range(power_fragments)),
                "Evaluation_of_quantity_sold_at_{}".format(t),
            )
            self.add_constraint(
                self.Qa[t] == sum(self.Qaf[t][i] for i in range(power_fragments)),
                "Evaluation_of_quantity_purchased_at_{}".format(t),
            )

            # StoredEnergy tracking constraint, evaluates the stock at each time step
            if t == self.start_date:
                self.add_constraint(
                    self.stored_energy[t]
                    == (
                        initial_stock
                        + self.time_step
                        / 60.0
                        * (
                            self.Qa[t] * self.equipment.charge_efficiency
                            - self.Qv[t] / self.equipment.discharge_efficiency
                        )
                    ),
                    "Stock_tracking_at_{}".format(t.add(minutes=self.time_step)),
                )
            else:
                (
                    self.add_constraint(
                        self.stored_energy[t]
                        == self.stored_energy[t.subtract(minutes=self.time_step)]
                        + self.time_step
                        / 60.0
                        * (
                            self.Qa[t] * self.equipment.charge_efficiency
                            - self.Qv[t] / self.equipment.discharge_efficiency
                        )
                    ),
                    "Stock_tracking_at_{}".format(t.add(minutes=self.time_step)),
                )

            # Respect of system states constraints (isSell and isV2G)
            self.add_constraint(
                self.Qv[t] <= self.is_sell[t] * self.equipment.maximum_power.get_value(t),
                "Respect_Pmax_sale_at_{}".format(t),
            )
            self.add_constraint(
                self.Qa[t] <= (1 - self.is_sell[t]) * abs(self.equipment.minimum_power.get_value(t)),
                "Respect_Pmax_purchase_at_{}".format(t),
            )
            self.add_constraint(self.Qv[t] >= 0, "Respect_Pmin_sale_at_{}".format(t))
            self.add_constraint(self.Qa[t] >= 0, "Respect_Pmin_purchase_at_{}".format(t))

            # Respect of minimum and maximum storage levels constraints
            self.add_constraint(
                self.stored_energy[t]
                >= (self.equipment.minimum_state_of_charge.get_value(t) * self.equipment.maximum_energy.get_value(t)),
                "Minimum_storage_level_constraint_at_{}".format(t),
            )
            self.add_constraint(
                self.stored_energy[t] <= self.equipment.maximum_energy.get_value(t),
                "Maximum_storage_level_constraint_at_{}".format(t),
            )

        # Respect of the balance between sales and purchases
        self.add_constraint(
            sum(self.Qa[t] for t in self.time_frame) * self.equipment.charge_efficiency
            == sum(self.Qv[t] for t in self.time_frame) / self.equipment.discharge_efficiency,
            "Respect_of_cycle_balance",
        )
