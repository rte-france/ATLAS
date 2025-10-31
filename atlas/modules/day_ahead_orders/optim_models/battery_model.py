"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum.duration import Duration

from atlas import Equipment
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.optim_models.dao_base_model import DAOBaseModel


class BatteryModel(DAOBaseModel):
    def __init__(
        self,
        parameters: DayAheadOrdersParameters,
        solver_name: str,
        name: str,
        equipment: Equipment,
        optimization_period: Duration,
    ):
        super().__init__(parameters, solver_name, name, equipment, optimization_period)

    def create_constraints(self, initial_stock: float | None, power_fragments: int) -> None:
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
                    f"Respect_of_sale_power_fragment_{i}_limit_at_{t}",
                )
                self.add_constraint(
                    self.Qaf[t][i] * power_fragments <= abs(self.equipment.minimum_power.get_value(t)),
                    f"Respect_of_purchase_power_fragment_{i}_limit_at_{t}",
                )

            # Total bought/sold energy at each time step is the sum of the fragments at time step
            self.add_constraint(
                self.get_variable(DAOBaseModel.sold_at_key(t)) == sum(self.Qvf[t][i] for i in range(power_fragments)),
                f"Evaluation_of_quantity_sold_at_{t}",
            )
            self.add_constraint(
                self.get_variable(DAOBaseModel.purchased_at_key(t))
                == sum(self.Qaf[t][i] for i in range(power_fragments)),
                f"Evaluation_of_quantity_purchased_at_{t}",
            )

            # StoredEnergy tracking constraint, evaluates the stock at each time step
            if t == self.parameters.start_date:
                self.add_constraint(
                    self.get_variable(DAOBaseModel.stored_energy_at_key(t))
                    == (
                        initial_stock
                        + self.parameters.time_step.total_hours()
                        * (
                            self.get_variable(DAOBaseModel.purchased_at_key(t)) * self.equipment.charge_efficiency
                            - self.get_variable(DAOBaseModel.sold_at_key(t)) / self.equipment.discharge_efficiency
                        )
                    ),
                    f"Stock_tracking_at_{t + self.parameters.time_step}",
                )
            else:
                self.add_constraint(
                    self.get_variable(DAOBaseModel.stored_energy_at_key(t))
                    == self.get_variable(DAOBaseModel.stored_energy_at_key(t - self.parameters.time_step))
                    + self.parameters.time_step.total_hours()
                    * (
                        self.get_variable(DAOBaseModel.purchased_at_key(t)) * self.equipment.charge_efficiency
                        - self.get_variable(DAOBaseModel.sold_at_key(t)) / self.equipment.discharge_efficiency
                    ),
                    f"Stock_tracking_at_{t + self.parameters.time_step}",
                )

            # Respect of system states constraints (isSell and isV2G)
            self.add_constraint(
                self.get_variable(DAOBaseModel.sold_at_key(t))
                <= self.get_variable(DAOBaseModel.is_sell_at_key(t)) * self.equipment.maximum_power.get_value(t),
                f"Respect_Pmax_sale_at_{t}",
            )
            self.add_constraint(
                self.get_variable(DAOBaseModel.purchased_at_key(t))
                <= (1 - self.get_variable(DAOBaseModel.is_sell_at_key(t)))
                * abs(self.equipment.minimum_power.get_value(t)),
                f"Respect_Pmax_purchase_at_{t}",
            )
            self.add_constraint(self.get_variable(DAOBaseModel.sold_at_key(t)) >= 0, f"Respect_Pmin_sale_at_{t}")
            self.add_constraint(
                self.get_variable(DAOBaseModel.purchased_at_key(t)) >= 0, f"Respect_Pmin_purchase_at_{t}"
            )

            # Respect of minimum and maximum storage levels constraints
            self.add_constraint(
                self.get_variable(DAOBaseModel.stored_energy_at_key(t))
                >= (self.equipment.minimum_state_of_charge.get_value(t) * self.equipment.maximum_energy.get_value(t)),
                f"Minimum_storage_level_constraint_at_{t}",
            )
            self.add_constraint(
                self.get_variable(DAOBaseModel.stored_energy_at_key(t)) <= self.equipment.maximum_energy.get_value(t),
                f"Maximum_storage_level_constraint_at_{t}",
            )

        # Respect of the balance between sales and purchases
        self.add_constraint(
            sum(self.get_variable(DAOBaseModel.purchased_at_key(t)) for t in self.time_frame)
            * self.equipment.charge_efficiency
            == sum(self.get_variable(DAOBaseModel.sold_at_key(t)) for t in self.time_frame)
            / self.equipment.discharge_efficiency,
            "Respect_of_cycle_balance",
        )
