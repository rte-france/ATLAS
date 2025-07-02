"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum

from atlas import OptimisationModel, Equipment, generate_datetimes
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters


class DAOBaseModel(OptimisationModel):
    def __init__(
        self,
        solver_name: str,
        name: str,
        parameters: DayAheadOrdersParameters,
        equipment: Equipment,
        optimization_period: int,
    ):
        super().__init__(solver_name, name)
        self._objective_direction = "maximize"
        self.parameters = parameters
        self.equipment = equipment
        self.optimizationPeriod = optimization_period
        # Get the price forecast from the input marker: estimations are at ActionHour, over the optimisation period
        # The price forecast is relative to the equipment's market area
        self.price_forecast = self.equipment.portfolio.market_area.price_forecast_medium.get_forecast(
            parameters.execution_date,
            parameters.start_date,
            parameters.end_date.add(hours=self.optimizationPeriod),
            pendulum.Duration(minutes=parameters.time_step),
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
        self.stored_energy = {}
        # Binary variable that represents the state of sale at each time step: 1 if selling, 0 if not
        self.is_sell = {}
        self.objective = None

    def create_decision_variables(self, nb_fragments: int):
        """Creation of decision variables"""

        for t in self.time_frame:
            self.Qv[t] = self.add_continuous_variable("Amount_sold_at_{}".format(t), 0)
            self.Qa[t] = self.add_continuous_variable("Amount_purchased_at_{}".format(t), 0)
            self.is_sell[t] = self.add_boolean_variable("isSell_at_{}".format(t))
            self.stored_energy[t] = self.add_continuous_variable("StoredEnergy_at_{}".format(t), 0)
            self.Qvf[t] = {}
            self.Qaf[t] = {}
            for i in range(nb_fragments):
                self.Qvf[t][i] = self.add_continuous_variable("Amount_sold_in_fragment_{}_at_{}".format(i, t), 0)
                self.Qaf[t][i] = self.add_continuous_variable("Amount_purchased_in_fragment_{}_at_{}".format(i, t), 0)

    def create_objective_function(self, nb_fragments: int, smoothing_factor: float):
        """Creation of objective function"""

        # The objective function is the total profit over the optimisation period
        if nb_fragments == 1:
            self.objective = (
                sum(
                    self.price_forecast.get_value(t) * self.Qvf[t][0] * self.parameters.time_step / 60.0
                    - self.price_forecast.get_value(t) * self.Qaf[t][0] * self.parameters.time_step / 60.0
                    for t in self.time_frame
                ),
                "Profit",
            )
        else:
            self.objective = (
                sum(
                    sum(
                        self.price_forecast.get_value(t)
                        * (1 - i * smoothing_factor / (nb_fragments - 1))
                        * self.Qvf[t][i]
                        * self.parameters.time_step
                        / 60.0
                        - self.price_forecast.get_value(t)
                        * (1 + i * smoothing_factor / (nb_fragments - 1))
                        * self.Qaf[t][i]
                        * self.parameters.time_step
                        / 60.0
                        for i in range(nb_fragments)
                    )
                    for t in self.time_frame
                ),
                "Profit",
            )
            self.solver.Maximize(self.objective[0])
