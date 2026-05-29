"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Literal

from pendulum import DateTime, Duration

from atlas.common.optimal_dispatch.dispatch.storage import StorageDispatch
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes


class StorageModel(OptimisationModel):
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
        self._dispatch: StorageDispatch = StorageDispatch(storage)

        if self.storage.portfolio.market_area.price_forecast_medium is not None:
            self.price_forecast: Timeseries = self.storage.portfolio.market_area.price_forecast_medium.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date + self.optimization_period,
                self.parameters.temporal.timestep,
            )
        else:
            raise AttributeError(f"{self.storage.portfolio.market_area.name} has no attribute 'price_forecast_medium'")

        self.time_frame: list[DateTime] = generate_datetimes(
            self.parameters.temporal.start_date,
            self.parameters.temporal.end_date + self.optimization_period - self.parameters.temporal.timestep,
            self.parameters.temporal.timestep,
        )

    def build_variables(self, nb_fragments: int) -> None:
        """Creation of decision variables."""
        self._dispatch.setup(self, self.parameters, nb_fragments)

        for t in self.time_frame:
            self._dispatch.add_variables(t)
            max_power = self.storage.maximum_power.get_value(t)
            min_power = self.storage.minimum_power.get_value(t)
            self._dispatch.add_fragment_variables(t, max_power, min_power)

    def build_objective(
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
        self.set_direction(direction)
        dt = self.parameters.temporal.timestep.total_hours()
        if nb_fragments == 1:
            self.add_objective(
                objective_expr=sum(
                    self.price_forecast.get_value(t)
                    * (
                        self._dispatch.get_fragment_sell_var(t, 0)
                        + self._dispatch.get_fragment_buy_var(t, 0)  # buy_n <= 0, so this subtracts cost
                    )
                    * dt
                    for t in self.time_frame
                )
            )
        else:
            self.add_objective(
                objective_expr=sum(
                    sum(
                        self.price_forecast.get_value(t)
                        * (1 - i * smoothing_factor / (nb_fragments - 1))
                        * self._dispatch.get_fragment_sell_var(t, i)
                        * dt
                        + self.price_forecast.get_value(t)
                        * (1 + i * smoothing_factor / (nb_fragments - 1))
                        * self._dispatch.get_fragment_buy_var(t, i)
                        * dt
                        for i in range(nb_fragments)
                    )
                    for t in self.time_frame
                )
            )
