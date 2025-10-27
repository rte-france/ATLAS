"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime, Duration

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes


class OtherNonDispatchablePO(OtherNonDispatchable):
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix

    optimisation_time_window: list[DateTime] = []

    def add_variables(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        """Build variables for non dispatchable equipment."""
        pass

    def add_constraints(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        This function formulates the non dispatchable equipments constraints.
        """
        pass

    def add_objective(
        self,
        model: OptimisationModel,
        time: DateTime,
        price_forecast: float,
        parameters: PortfolioOptimisationParameters,
    ):
        pass

    def get_optimisation_time_window(
        self, start_date: DateTime, end_date: DateTime, timestep: Duration
    ) -> list[DateTime]:
        """Get optimisation time windows based on additional hours."""

        self.optimisation_time_window = generate_datetimes(
            start=start_date, end=end_date + self.additional_hours, freq=timestep
        )
        return self.optimisation_time_window
