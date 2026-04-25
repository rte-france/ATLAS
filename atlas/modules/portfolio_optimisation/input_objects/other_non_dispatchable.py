"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime, Duration

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.objects.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.solver.solver_interface import OptimisationModel


class OtherNonDispatchablePO(OtherNonDispatchable):
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    additional_hours: Duration

    optimisation_time_window: list[DateTime] = []

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        """
        Build variables for non dispatchable equipment.

        :param model: Optimization model
        :type model: OptimisationModel
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        """
        pass

    def add_constraints(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        This function formulates the non dispatchable equipments constraints.
        """
        pass

    def add_objective(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
        price_forecasts: dict = {},
    ):
        pass
