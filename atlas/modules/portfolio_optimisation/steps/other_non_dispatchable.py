"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.modules.portfolio_optimisation.input_objects.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.steps.base import AbstractOptimStep
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class OtherNonDispatchableStep(AbstractOptimStep[OtherNonDispatchablePO]):
    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        pass

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        pass

    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict | None = None
    ):
        pass
