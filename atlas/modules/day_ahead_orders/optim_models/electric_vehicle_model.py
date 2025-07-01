"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum

from atlas import OptimisationModel, generate_datetimes, Equipment
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters


class ElectricVehicleModel(OptimisationModel):
    def __init__(self, name: str, solver_name: str, parameters: DayAheadOrdersParameters, equipment: Equipment):
        super().__init__(solver_name, name)
        self._objective_direction = "maximize"
        self.parameters = parameters
        self.equipment = equipment
        self.optimizationPeriod = parameters.ev_additional_hours
        # Get the price forecast from the input marker: estimations are at ActionHour, over the optimisation period
        # The price forecast is relative to the equipment's market area
        self.price_forecast = self.equipment.portfolio.market_area.price_forecast_medium.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_date.add(hours=self.optimizationPeriod)
        )
        # Set-up the time frames
        # Definition of the time_frame time frame: the time frame on which
        # the optimization program will be solved.
        # Remark: we define the time series until end_date - time_step because
        # we want all time steps to lie in the [start_date, endOptimizationDate] range.
        self.time_frame = generate_datetimes(
            parameters.start_date,
            parameters.end_date.add(hours=self.optimizationPeriod).subtract(minutes=parameters.time_step),
            pendulum.duration(minutes=parameters.time_step),
        )
        # Total quantities bought and purchased in the market at each time step
        self.Qv = {}
        self.Qa = {}
        # Quantities bought and purchased in each fragment of power i at each time step
        self.Qvf = {}
        self.Qaf = {}
        # Energy stored in battery at each time step
        # StoredEnergy[t] corresponds to the energy stord in battery at t + 1
        self.StoredEnergy = {}
        # Binary variable that represents the state of sale at each time step: 1 if selling, 0 if not
        self.isSell = {}
        self.objective = None

    def create_decision_variables(self):
        """Creation of decision variables"""

        for t in self.time_frame:
            self.Qv[t] = self.add_continuous_variable("Amount_sold_at_{}".format(t), 0)
            self.Qa[t] = self.add_continuous_variable("Amount_purchased_at_{}".format(t), 0)
            self.isSell[t] = self.add_boolean_variable("isSell_at_{}".format(t))
            self.StoredEnergy[t] = self.add_continuous_variable("StoredEnergy_at_{}".format(t), 0)
            self.Qvf[t] = {}
            self.Qaf[t] = {}
            for i in range(self.parameters.ev_nb_fragments):
                self.Qvf[t][i] = self.add_continuous_variable("Amount_sold_in_fragment_{}_at_{}".format(i, t), 0)
                self.Qaf[t][i] = self.add_continuous_variable("Amount_purchased_in_fragment_{}_at_{}".format(i, t), 0)

    def create_objective_function(self):
        """Creation of objective function"""

        # The objective function is the total profit over the optimisation period
        if self.parameters.ev_nb_fragments == 1:
            self.objective = (
                sum(
                    self.price_forecast.GetValue(t) * self.Qvf[t][0] * self.parameters.time_step / 60.0
                    - self.price_forecast.GetValue(t) * self.Qaf[t][0] * self.parameters.time_step / 60.0
                    for t in self.time_frame
                ),
                "Profit",
            )
        else:
            self.objective = (
                sum(
                    sum(
                        self.price_forecast.GetValue(t)
                        * (1 - i * self.parameters.ev_smoothing_factor / (self.parameters.ev_nb_fragments - 1))
                        * self.Qvf[t][i]
                        * self.parameters.time_step
                        / 60.0
                        - self.price_forecast.GetValue(t)
                        * (1 + i * self.parameters.ev_smoothing_factor / (self.parameters.ev_nb_fragments - 1))
                        * self.Qaf[t][i]
                        * self.parameters.time_step
                        / 60.0
                        for i in range(self.parameters.ev_nb_fragments)
                    )
                    for t in self.time_frame
                ),
                "Profit",
            )
            self.solver.Maximize(self.objective[0])

    def create_constraints(self, InitialStock: float | None):
        # Creation of constraints

        for t in self.time_frame:
            for i in range(self.parameters.ev_nb_fragments):
                self.add_constraint(
                    self.Qvf[t][i] * self.parameters.ev_nb_fragments <= self.equipment.MaximumPower.GetValue(t),
                    "Respect_of_sale_power_fragment_{}_limit_at_{}".format(i, t),
                )
                self.add_constraint(
                    self.Qaf[t][i] * self.parameters.ev_nb_fragments <= abs(self.equipment.MinimumPower.GetValue(t)),
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
                    self.StoredEnergy[t]
                    == (
                        InitialStock
                        * (
                            self.equipment.MaximumEnergy.GetValue(t)
                            / self.equipment.MaximumEnergy.GetValue(t.subtract(minutes=self.parameters.time_step))
                        )
                        + self.parameters.time_step
                        / 60.0
                        * (
                            self.Qa[t] * self.equipment.ChargeEfficiency
                            - self.Qv[t] / self.equipment.DischargeEfficiency
                        )
                        + (
                            self.equipment.DisplacementEnergy.GetValue(t)
                            - self.equipment.DisplacementEnergy.GetValue(t.subtract(minutes=self.parameters.time_step))
                        )
                    ),
                    "Stock_tracking_at_{}".format(t),
                )
            else:
                self.add_constraint(
                    self.StoredEnergy[t]
                    == (
                        self.StoredEnergy[t.subtract(minutes=self.parameters.time_step)]
                        * (
                            self.equipment.MaximumEnergy.GetValue(t)
                            / self.equipment.MaximumEnergy.GetValue(t.subtract(minutes=self.parameters.time_step))
                        )
                        + self.parameters.time_step
                        / 60.0
                        * (
                            self.Qa[t] * self.equipment.ChargeEfficiency
                            - self.Qv[t] / self.equipment.DischargeEfficiency
                        )
                        + (
                            self.equipment.DisplacementEnergy.GetValue(t)
                            - self.equipment.DisplacementEnergy.GetValue(t.subtract(minutes=self.parameters.time_step))
                        )
                    ),
                    "Stock_tracking_at_{}".format(t),
                )

            # Respect of system states constraints (isSell and isV2G)
            self.add_constraint(
                self.Qv[t] <= self.equipment.isV2G * self.isSell[t] * self.equipment.MaximumPower.GetValue(t),
                "Respect_Pmax_sale_at_{}".format(t),
            )
            self.add_constraint(
                self.Qa[t]
                <= (1 - self.isSell[t] * self.equipment.isV2G) * abs(self.equipment.MinimumPower.GetValue(t)),
                "Respect_Pmax_purchase_at_{}".format(t),
            )
            self.add_constraint(self.Qv[t] >= 0, "Respect_Pmin_sale_at_{}".format(t))
            self.add_constraint(self.Qa[t] >= 0, "Respect_Pmin_purchase_at_{}".format(t))

            # Respect of minimum and maximum stoage level constraints
            self.add_constraint(
                self.StoredEnergy[t]
                >= self.equipment.MinimumStateOfCharge.GetValue(t) * self.equipment.MaximumEnergy.GetValue(t),
                "Minimum_storage_level_constraint_at_{}".format(t),
            )
            self.add_constraint(
                self.StoredEnergy[t] <= self.equipment.MaximumEnergy.GetValue(t),
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
                OPPROB += Qv[t] * (1 - Equipment.MinimumStateOfCharge.GetValue(t)) <= (Equipment.isV2G * Equipment.MaximumPower.GetValue(t) *
                                                                                  (InitialStock/Equipment.MaximumEnergy.GetValue(t.AddMinutes(-p.time_step)) -
                                                                                   Equipment.MinimumStateOfCharge.GetValue(t.AddMinutes(-p.time_step))) *
                                                                                  Equipment.DischargeEfficiency), "Adjustment_of_Pmax_sale_at_{}".format(t)
                OPPROB += Qa[t] * (1 - Equipment.MinimumStateOfCharge.GetValue(t)) <= (Equipment.MaximumPower.GetValue(t) *
                                                                                  (1 - InitialStock/Equipment.MaximumEnergy.GetValue(t.AddMinutes(-p.time_step))) /
                                                                                  Equipment.ChargeEfficiency) , "Adjustment_of_Pmax_purchase_at_{}".format(t)
            else:
                OPPROB += Qv[t] * (1 - Equipment.MinimumStateOfCharge.GetValue(t)) <= (Equipment.isV2G * Equipment.MaximumPower.GetValue(t) *
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
            sum(self.Qa[t] for t in self.time_frame) * self.equipment.ChargeEfficiency
            >= (
                self.equipment.DisplacementEnergy.GetValue(
                    self.parameters.end_date.add(hours=self.optimizationPeriod).subtract(
                        minutes=self.parameters.time_step
                    )
                )
                - self.equipment.DisplacementEnergy.GetValue(
                    self.parameters.start_date.subtract(minutes=self.parameters.time_step)
                )
            )
            * self.parameters.ev_energy_coef,
            "DisplacementEnergy_compensation_for_{}".format(str(self.equipment.Name)),
        )
