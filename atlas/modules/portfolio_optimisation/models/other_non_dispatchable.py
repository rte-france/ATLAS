"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class OtherNonDispatchablePO(OtherNonDispatchable):
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix

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
