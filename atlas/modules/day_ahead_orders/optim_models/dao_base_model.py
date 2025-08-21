"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

import pendulum
from pydantic_extra_types.pendulum_dt import DateTime

from atlas import Equipment, OptimisationModel, generate_datetimes


class DAOBaseModel(OptimisationModel):
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
        super().__init__(solver_name, name)
        self._objective_direction = "maximize"
        self.start_date = start_date
        self.end_date = end_date
        self.execution_date = execution_date
        self.time_step = time_step
        self.equipment = equipment
        self.optimizationPeriod = optimization_period
        # Get the price forecast from the input marker: estimations are at ActionHour, over the optimisation period
        # The price forecast is relative to the equipment's market area
        self.price_forecast = self.equipment.portfolio.market_area.price_forecast_medium.get_forecast(
            self.execution_date,
            self.start_date,
            self.end_date.add(hours=self.optimizationPeriod),
            pendulum.Duration(minutes=self.time_step),
        )
        # Set-up the time frames
        # Definition of the time_frame time frame: the time frame on which
        # the optimization program will be solved.
        # Remark: we define the time series until end_date - time_step because
        # we want all time steps to lie in the [start_date, endOptimizationDate] range.
        self.time_frame = generate_datetimes(
            self.start_date,
            self.end_date.add(hours=self.optimizationPeriod).subtract(minutes=self.time_step),
            pendulum.duration(minutes=self.time_step),
        )
        # Total quantities bought and purchased in the market at each time step
        self.Qv: dict[DateTime, Any] = {}  # Qv: dict[Datetime, Any]
        self.Qa: dict[DateTime, Any] = {}
        # Quantities bought and purchased in each fragment of power i at each time step
        self.Qvf: dict[DateTime, Any] = {}
        self.Qaf: dict[DateTime, Any] = {}
        # Energy stored in battery at each time step
        # StoredEnergy[t] corresponds to the energy stord in battery at t + 1
        self.stored_energy: dict[DateTime, Any] = {}
        # Binary variable that represents the state of sale at each time step: 1 if selling, 0 if not
        self.is_sell: dict[DateTime, Any] = {}
        self.objective = None

    def create_decision_variables(self, nb_fragments: int):
        """Creation of decision variables"""

        for t in self.time_frame:
            self.Qv[t] = self.add_continuous_variable(f"Amount_sold_at_{t}", 0)
            self.Qa[t] = self.add_continuous_variable(f"Amount_purchased_at_{t}", 0)
            self.is_sell[t] = self.add_boolean_variable(f"isSell_at_{t}")
            self.stored_energy[t] = self.add_continuous_variable(f"StoredEnergy_at_{t}", 0)
            self.Qvf[t] = {}
            self.Qaf[t] = {}
            for i in range(nb_fragments):
                self.Qvf[t][i] = self.add_continuous_variable(f"Amount_sold_in_fragment_{i}_at_{t}", 0)
                self.Qaf[t][i] = self.add_continuous_variable(f"Amount_purchased_in_fragment_{i}_at_{t}", 0)

    def create_objective_function(self, nb_fragments: int, smoothing_factor: float):
        """Creation of objective function"""

        # The objective function is the total profit over the optimisation period
        if nb_fragments == 1:
            self.objective = (
                sum(
                    self.price_forecast.get_value(t) * self.Qvf[t][0] * self.time_step / 60.0
                    - self.price_forecast.get_value(t) * self.Qaf[t][0] * self.time_step / 60.0
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
                        * self.time_step
                        / 60.0
                        - self.price_forecast.get_value(t)
                        * (1 + i * smoothing_factor / (nb_fragments - 1))
                        * self.Qaf[t][i]
                        * self.time_step
                        / 60.0
                        for i in range(nb_fragments)
                    )
                    for t in self.time_frame
                ),
                "Profit",
            )
            self.solver.Maximize(self.objective[0])
