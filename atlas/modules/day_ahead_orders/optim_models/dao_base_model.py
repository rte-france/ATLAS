"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import os
from typing import Any, Literal

from pendulum.duration import Duration
from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas import Equipment, OptimisationModel, generate_datetimes
from atlas.enum import SolverEnum
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters


class DAOBaseModel(OptimisationModel):
    AMOUNT_SOLD_AT = "Amount_sold_at_"
    AMOUNT_PURCHASED_AT = "Amount_purchased_at_"
    IS_SELL_AT = "isSell_at_"
    STORED_ENERGY_AT = "StoredEnergy_at_"
    AMOUNT_SOLD_IN_FRAGMENT = "Amount_sold_in_fragment_"
    AMOUNT_PURCHASED_IN_FRAGMENT = "Amount_purchased_in_fragment_"

    def __init__(
        self,
        parameters: DayAheadOrdersParameters,
        solver_name: str,
        name: str,
        equipment: Equipment,
        optimization_period: Duration,
    ):
        super().__init__(solver_name, name)
        self.parameters = parameters
        self.equipment = equipment
        self.optimizationPeriod = optimization_period
        # Get the price forecast from the input marker: estimations are at ActionHour, over the optimisation period
        # The price forecast is relative to the equipment's market area
        self.price_forecast = self.equipment.portfolio.market_area.price_forecast_medium.get_forecast(
            self.parameters.execution_date,
            self.parameters.start_date,
            self.parameters.end_date + self.optimizationPeriod,
            self.parameters.time_step,
        )
        # Set-up the time frames
        # Definition of the time_frame time frame: the time frame on which
        # the optimization program will be solved.
        # Remark: we define the time series until end_date - time_step because
        # we want all time steps to lie in the [start_date, endOptimizationDate] range.
        self.time_frame = generate_datetimes(
            self.parameters.start_date,
            self.parameters.end_date + self.optimizationPeriod - self.parameters.time_step,
            self.parameters.time_step,
        )

    @classmethod
    def sold_at_key(cls, t):
        return f"{cls.AMOUNT_SOLD_AT}{t}"

    @classmethod
    def purchased_at_key(cls, t):
        return f"{cls.AMOUNT_PURCHASED_AT}{t}"

    @classmethod
    def is_sell_at_key(cls, t):
        return f"{cls.IS_SELL_AT}{t}"

    @classmethod
    def stored_energy_at_key(cls, t):
        return f"{cls.STORED_ENERGY_AT}{t}"

    @classmethod
    def amount_sold_in_fragment_at_key(cls, t, i):
        return f"{cls.AMOUNT_SOLD_IN_FRAGMENT}{i}_at_{t}"

    @classmethod
    def amount_purchased_in_fragment_at_key(cls, t, i):
        return f"{cls.AMOUNT_PURCHASED_IN_FRAGMENT}{i}_at_{t}"

    def create_decision_variables(self, nb_fragments: int) -> None:
        """Creation of decision variables"""

        for t in self.time_frame:
            # Total quantities bought and purchased in the market at each time step
            self.add_continuous_variable(DAOBaseModel.sold_at_key(t), 0)
            self.add_continuous_variable(DAOBaseModel.purchased_at_key(t), 0)
            # Binary variable that represents the state of sale at each time step: 1 if selling, 0 if not
            self.add_boolean_variable(DAOBaseModel.is_sell_at_key(t))
            # Energy stored in battery at each time step
            # StoredEnergy[t] corresponds to the energy stord in battery at t + 1
            self.add_continuous_variable(DAOBaseModel.stored_energy_at_key(t), 0)
            # Quantities bought and purchased in each fragment of power i at each time step
            for i in range(nb_fragments):
                self.add_continuous_variable(DAOBaseModel.amount_sold_in_fragment_at_key(t, i), 0)
                self.add_continuous_variable(DAOBaseModel.amount_purchased_in_fragment_at_key(t, i), 0)

    def create_objective_function(
        self, nb_fragments: int, smoothing_factor: float, direction: Literal["maximize", "minimize"] = "maximize"
    ) -> None:
        """Creation of objective function"""

        # The objective function is the total profit over the optimisation period
        if nb_fragments == 1:
            self.add_objective(
                objective_expr=sum(
                    self.price_forecast.get_value(t)
                    * self.get_variable(DAOBaseModel.amount_sold_in_fragment_at_key(t, 0))
                    * self.parameters.time_step.total_hours()
                    - self.price_forecast.get_value(t)
                    * self.get_variable(DAOBaseModel.amount_purchased_in_fragment_at_key(t, 0))
                    * self.parameters.time_step.total_hours()
                    for t in self.time_frame
                ),
                direction=direction,
            )
        else:
            self.add_objective(
                objective_expr=sum(
                    sum(
                        self.price_forecast.get_value(t)
                        * (1 - i * smoothing_factor / (nb_fragments - 1))
                        * self.get_variable(DAOBaseModel.amount_sold_in_fragment_at_key(t, i))
                        * self.parameters.time_step.total_hours()
                        - self.price_forecast.get_value(t)
                        * (1 + i * smoothing_factor / (nb_fragments - 1))
                        * self.get_variable(DAOBaseModel.amount_purchased_in_fragment_at_key(t, i))
                        * self.parameters.time_step.total_hours()
                        for i in range(nb_fragments)
                    )
                    for t in self.time_frame
                ),
                direction=direction,
            )

    def solve_with_xpress(self) -> None:
        if self.solver_name != SolverEnum.XPRESS:
            # If another solver is being used, consider setting the NoOverlap parameter to False as it previously raised errors otherwise with GLPK
            raise ValueError(
                "Please use XPRESS, as other solvers either are deprecated or provide non-optimal solutions"
            )

        if self.parameters.debug:
            lp_file_name = os.path.join(self.parameters.output_folder, f"storage_{self.equipment.name}.lp")
            self.export_model(lp_file_name)

        self.solve(self.parameters.solver_time_out.total_minutes())

        if self.parameters.verbose:
            cfg.logger.info(f"Solver status: {self.solution_info.status}")
            cfg.logger.info(f"Objective function value: {self._objective}")
