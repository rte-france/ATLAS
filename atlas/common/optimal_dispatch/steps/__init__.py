"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from atlas.abstract_class.parameters import AbstractModuleParameters
    from atlas.solver.solver_interface import OptimisationModel

T = TypeVar("T")
P = TypeVar("P", bound="AbstractModuleParameters")


class AbstractOptimStep[T, P](ABC):
    """
    Abstract base for per-equipment LP/MIP optimisation steps.

    Generic over:
    - ``T``: the equipment type the step operates on (e.g. ``ThermalDAO``).
    - ``P``: the module-parameters type the step expects (e.g. ``DayAheadOrdersParameters``).
      Bounded by :class:`~atlas.abstract_class.parameters.AbstractModuleParameters` so subclasses
      can narrow it to their concrete parameter object without violating LSP.
    """

    def __init__(self, equipment: T) -> None:
        self.equipment = equipment

    @abstractmethod
    def add_variables(self, model: OptimisationModel, parameters: P) -> None: ...

    @abstractmethod
    def add_constraints(self, model: OptimisationModel, parameters: P) -> None: ...

    @abstractmethod
    def add_objective(self, model: OptimisationModel, parameters: P, price_forecasts: dict | None = None) -> None: ...
