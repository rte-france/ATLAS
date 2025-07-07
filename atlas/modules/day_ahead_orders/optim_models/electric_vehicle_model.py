"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import Equipment
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.optim_models.dao_base_model import DAOBaseModel


class ElectricVehicleModel(DAOBaseModel):
    def __init__(
        self,
        solver_name: str,
        name: str,
        parameters: DayAheadOrdersParameters,
        equipment: Equipment,
        optimization_period: int,
    ):
        super().__init__(solver_name, name, parameters, equipment, optimization_period)

    def create_constraints(self, initial_stock: float | None):
        # Creation of constraints

        for t in self.time_frame:
            for i in range(self.parameters.ev_nb_fragments):
                self.add_constraint(
                    self.Qvf[t][i] * self.parameters.ev_nb_fragments <= self.equipment.maximum_power.get_value(t),
                    "Respect_of_sale_power_fragment_{}_limit_at_{}".format(i, t),
                )
                self.add_constraint(
                    self.Qaf[t][i] * self.parameters.ev_nb_fragments <= abs(self.equipment.minimum_power.get_value(t)),
                    "Respect_of_purchase_power_fragment_{}_limit_at_{}".format(i, t),
                )

            # Total bought/sold energy at each tome step is the sum of the fragments at time step
            self.add_constraint(
                self.Qv[t] == sum(self.Qvf[t][i] for i in range(self.parameters.ev_nb_fragments)),
                "Evaluation_of_quantity_sold_at_{}".format(t),
            )
            self.add_constraint(
                self.Qa[t] == sum(self.Qaf[t][i] for i in range(self.parameters.ev_nb_fragments)),
                "Evaluation_of_quantity_purchased_at_{}".format(t),
            )

            # StoredEnergy tracking constraint, evaluates the stock at each time step
            if t == self.parameters.start_date:
                self.add_constraint(
                    self.stored_energy[t]
                    == (
                        initial_stock
                        * (
                            self.equipment.maximum_energy.get_value(t)
                            / self.equipment.maximum_energy.get_value(t.subtract(minutes=self.parameters.time_step))
                        )
                        + self.parameters.time_step
                        / 60.0
                        * (
                            self.Qa[t] * self.equipment.charge_efficiency
                            - self.Qv[t] / self.equipment.discharge_efficiency
                        )
                        + (
                            self.equipment.displacement_energy.get_value(t)
                            - self.equipment.displacement_energy.get_value(
                                t.subtract(minutes=self.parameters.time_step)
                            )
                        )
                    ),
                    "Stock_tracking_at_{}".format(t),
                )
            else:
                self.add_constraint(
                    self.stored_energy[t]
                    == (
                        self.stored_energy[t.subtract(minutes=self.parameters.time_step)]
                        * (
                            self.equipment.maximum_energy.get_value(t)
                            / self.equipment.maximum_energy.get_value(t.subtract(minutes=self.parameters.time_step))
                        )
                        + self.parameters.time_step
                        / 60.0
                        * (
                            self.Qa[t] * self.equipment.charge_efficiency
                            - self.Qv[t] / self.equipment.discharge_efficiency
                        )
                        + (
                            self.equipment.displacement_energy.get_value(t)
                            - self.equipment.displacement_energy.get_value(
                                t.subtract(minutes=self.parameters.time_step)
                            )
                        )
                    ),
                    "Stock_tracking_at_{}".format(t),
                )

            # Respect of system states constraints (isSell and is_v2g)
            self.add_constraint(
                self.Qv[t] <= self.equipment.is_v2g * self.is_sell[t] * self.equipment.maximum_power.get_value(t),
                "Respect_Pmax_sale_at_{}".format(t),
            )
            self.add_constraint(
                self.Qa[t]
                <= (1 - self.is_sell[t] * self.equipment.is_v2g) * abs(self.equipment.maximum_power.get_value(t)),
                "Respect_Pmax_purchase_at_{}".format(t),
            )
            self.add_constraint(self.Qv[t] >= 0, "Respect_Pmin_sale_at_{}".format(t))
            self.add_constraint(self.Qa[t] >= 0, "Respect_Pmin_purchase_at_{}".format(t))

            # Respect of minimum and maximum stoage level constraints
            self.add_constraint(
                self.stored_energy[t]
                >= self.equipment.minimum_state_of_charge.get_value(t) * self.equipment.maximum_energy.get_value(t),
                "Minimum_storage_level_constraint_at_{}".format(t),
            )
            self.add_constraint(
                self.stored_energy[t] <= self.equipment.maximum_energy.get_value(t),
                "Maximum_storage_level_constraint_at_{}".format(t),
            )

            # Create additional constraints linked with MaximumPower, to represent the fact that a part of the EV fleet
            # is going to be fully charged / discharged (depending on the ratio between StoredEnergy and MaximumEnergy, and possibly MinimumStateOfCharge),
            # meaning that it will not be able to purcharse / sell energy.
            # Explanation note: the ratio that determines the part of the fleet that is fully charged or discharged is evaluated
            # on the previous time step, since StoredEnergy(t) is unkown prior to the optimization. This is assumed to be a good estimation
            # of the ratio at t. Every other value is taken at t.
            # FC: We need to recode this one, the concept is very interesting but solving the optimization
            # becomes exponentially longer with each additional hour. And currently impossible to solve for 7 days.
            """
            if t == p.start_date:
                OPPROB += Qv[t] * (1 - Equipment.MinimumStateOfCharge.GetValue(t)) <= (Equipment.is_v2g * Equipment.MaximumPower.GetValue(t) *
                                                                                  (InitialStock/Equipment.MaximumEnergy.GetValue(t.AddMinutes(-p.time_step)) -
                                                                                   Equipment.MinimumStateOfCharge.GetValue(t.AddMinutes(-p.time_step))) *
                                                                                  Equipment.DischargeEfficiency), "Adjustment_of_Pmax_sale_at_{}".format(t)
                OPPROB += Qa[t] * (1 - Equipment.MinimumStateOfCharge.GetValue(t)) <= (Equipment.MaximumPower.GetValue(t) *
                                                                                  (1 - InitialStock/Equipment.MaximumEnergy.GetValue(t.AddMinutes(-p.time_step))) /
                                                                                  Equipment.ChargeEfficiency) , "Adjustment_of_Pmax_purchase_at_{}".format(t)
            else:
                OPPROB += Qv[t] * (1 - Equipment.MinimumStateOfCharge.GetValue(t)) <= (Equipment.is_v2g * Equipment.MaximumPower.GetValue(t) *
                                                                                  (StoredEnergy[t.AddMinutes(-p.time_step)]/Equipment.MaximumEnergy.GetValue(t.AddMinutes(-p.time_step)) -
                                                                                   Equipment.MinimumStateOfCharge.GetValue(t.AddMinutes(-p.time_step))) *
                                                                                  Equipment.DischargeEfficiency), "Adjustment_of_Pmax_sale_at_{}".format(t)
                OPPROB += Qa[t] * (1 - Equipment.MinimumStateOfCharge.GetValue(t)) <= (Equipment.MaximumPower.GetValue(t) *
                                                                                  (1 - StoredEnergy[t.AddMinutes(-p.time_step)]/
                                                                                   Equipment.MaximumEnergy.GetValue(t.AddMinutes(-p.time_step))) /
                                                                                  Equipment.ChargeEfficiency) , "Adjustment_of_Pmax_purchase_at_{}".format(t)

            """

        # Constraint on Qa to compensate at least the delta of Displacement Energy over the entire optimization time frame
        self.add_constraint(
            sum(self.Qa[t] for t in self.time_frame) * self.equipment.charge_efficiency
            >= (
                self.equipment.displacement_energy.get_value(
                    self.parameters.end_date.add(hours=self.optimizationPeriod).subtract(
                        minutes=self.parameters.time_step
                    )
                )
                - self.equipment.displacement_energy.get_value(
                    self.parameters.start_date.subtract(minutes=self.parameters.time_step)
                )
            )
            * self.parameters.ev_energy_coef,
            "DisplacementEnergy_compensation_for_{}".format(str(self.equipment.name)),
        )
