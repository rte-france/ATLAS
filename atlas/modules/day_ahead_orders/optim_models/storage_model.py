"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Literal

from pendulum import DateTime
from pendulum.duration import Duration

import atlas.config as cfg
from atlas import OptimisationModel, SolverOptions, Timeseries, generate_datetimes
from atlas.enum import SolverEnum
from atlas.modules.day_ahead_orders.data_models.storage import StorageDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters


class StorageModel(OptimisationModel):
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
        super().__init__(solver_name, name, solver_options)
        self.parameters: DayAheadOrdersParameters = parameters
        self.storage: StorageDAO = storage
        self.optimization_period: Duration = optimization_period
        # Get the price forecast from the dataset: estimations are at ActionHour, over the optimization period
        # The price forecast is relative to the equipment's market area
        self.price_forecast: Timeseries = self.storage.portfolio.market_area.price_forecast_medium.get_forecast(
            self.parameters.execution_date,
            self.parameters.start_date,
            self.parameters.end_date + self.optimization_period,
            self.parameters.timestep,
        )
        # Set-up the time frames
        # Definition of the time_frame time frame: the time frame on which
        # the optimization program will be solved.
        # Remark: we define the time series until end_date - time_step because
        # we want all time steps to lie in the [start_date, end_optimization_date] range.
        self.time_frame: list[DateTime] = generate_datetimes(
            self.parameters.start_date,
            self.parameters.end_date + self.optimization_period - self.parameters.timestep,
            self.parameters.timestep,
        )

    @classmethod
    def sold_at_key(cls, t: DateTime) -> str:
        return f"{cls.AMOUNT_SOLD_AT}{t}"

    @classmethod
    def purchased_at_key(cls, t: DateTime) -> str:
        return f"{cls.AMOUNT_PURCHASED_AT}{t}"

    @classmethod
    def is_sell_at_key(cls, t: DateTime) -> str:
        return f"{cls.IS_SELL_AT}{t}"

    @classmethod
    def stored_energy_at_key(cls, t: DateTime) -> str:
        return f"{cls.STORED_ENERGY_AT}{t}"

    @classmethod
    def amount_sold_in_fragment_at_key(cls, t: DateTime, i: int) -> str:
        return f"{cls.AMOUNT_SOLD_IN_FRAGMENT}{i}_at_{t}"

    @classmethod
    def amount_purchased_in_fragment_at_key(cls, t: DateTime, i: int) -> str:
        return f"{cls.AMOUNT_PURCHASED_IN_FRAGMENT}{i}_at_{t}"

    def create_decision_variables(self, nb_fragments: int) -> None:
        """Creation of decision variables"""

        for t in self.time_frame:
            # Total quantities bought and purchased in the market at each time step
            self.add_continuous_variable(StorageModel.sold_at_key(t), 0)
            self.add_continuous_variable(StorageModel.purchased_at_key(t), 0)
            # Binary variable that represents the state of sale at each time step: 1 if selling, 0 if not
            self.add_boolean_variable(StorageModel.is_sell_at_key(t))
            # Energy stored in battery at each time step
            # StoredEnergy[t] corresponds to the energy stord in battery at t + 1
            self.add_continuous_variable(StorageModel.stored_energy_at_key(t), 0)
            # Quantities bought and purchased in each fragment of power i at each time step
            for i in range(nb_fragments):
                self.add_continuous_variable(StorageModel.amount_sold_in_fragment_at_key(t, i), 0)
                self.add_continuous_variable(StorageModel.amount_purchased_in_fragment_at_key(t, i), 0)

    def create_objective_function(
        self, nb_fragments: int, smoothing_factor: float, direction: Literal["maximize", "minimize"] = "maximize"
    ) -> None:
        """
        Creation of objective function
        :param nb_fragments: number of fragments
        :type nb_fragments: int
        :param smoothing_factor: smoothing factor
        :type smoothing_factor: float
        :param direction: direction
        :type direction: Literal["maximize", "minimize"]
        :return: None
        """

        # The objective function is the total profit over the optimisation period
        self.set_direction(direction)
        if nb_fragments == 1:
            self.add_objective(
                objective_expr=sum(
                    self.price_forecast.get_value(t)
                    * self.get_variable(StorageModel.amount_sold_in_fragment_at_key(t, 0))
                    * self.parameters.timestep.total_hours()
                    - self.price_forecast.get_value(t)
                    * self.get_variable(StorageModel.amount_purchased_in_fragment_at_key(t, 0))
                    * self.parameters.timestep.total_hours()
                    for t in self.time_frame
                )
            )
        else:
            self.add_objective(
                objective_expr=sum(
                    sum(
                        self.price_forecast.get_value(t)
                        * (1 - i * smoothing_factor / (nb_fragments - 1))
                        * self.get_variable(StorageModel.amount_sold_in_fragment_at_key(t, i))
                        * self.parameters.timestep.total_hours()
                        - self.price_forecast.get_value(t)
                        * (1 + i * smoothing_factor / (nb_fragments - 1))
                        * self.get_variable(StorageModel.amount_purchased_in_fragment_at_key(t, i))
                        * self.parameters.timestep.total_hours()
                        for i in range(nb_fragments)
                    )
                    for t in self.time_frame
                )
            )

    def solve_model(self) -> None:
        """
        Solve the optimization problem
        :return: None
        """
        if self.solver_name != SolverEnum.XPRESS:
            # If another solver is being used, consider setting the NoOverlap parameter to False as it previously raised errors otherwise with GLPK
            cfg.logger.warning(
                "Please use XPRESS, as other solvers either are deprecated or provide non-optimal solutions"
            )

        if self.parameters.export_lp:
            lp_file_name = self.parameters.output_folder / f"storage_{self.storage.name}.lp"
            self.export_model(str(lp_file_name))

        self.solve()

        if self.parameters.verbose:
            status = self.solution_info.status if self.solution_info else None
            cfg.logger.info(f"Solver status: {status}")
            cfg.logger.info(f"Objective function value: {self._objective}")
