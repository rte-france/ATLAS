"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
    from atlas.solver.solver_interface import OptimisationModel

T = TypeVar("T")


class AbstractOptimStep(ABC, Generic[T]):
    def __init__(self, equipment: T):
        self.equipment = equipment

    @abstractmethod
    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters) -> None: ...

    @abstractmethod
    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters) -> None: ...

    @abstractmethod
    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict | None = None
    ) -> None: ...
