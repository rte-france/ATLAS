"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pendulum import DateTime

    from atlas.solver.temporal_variable import Bound, TemporalVariable


class ReserveHandler(ABC):
    """
    Base class for reserve variable/constraint builders.

    Owns the model binding and the reserve temporal variables shared by every equipment,
    named ``{prefix}_{name}`` (so ``{prefix}_{name}_{time}`` in the solver). Their bounds and
    the equipment-specific variables and constraints are declared in subclasses. Instances are
    not created directly — use :class:`ReserveFactory`.
    """

    def __init__(self, name: str, maximum_automated: float) -> None:
        self._name = name
        self._maximum_automated = maximum_automated
        self._model: OptimisationModel | None = None

        self.reserves_up: TemporalVariable
        self.reserves_down: TemporalVariable
        self.unprovided_reserves_up: TemporalVariable
        self.unprovided_reserves_down: TemporalVariable
        self.automated_reserves_up: TemporalVariable
        self.automated_reserves_down: TemporalVariable

    def setup(self, model: OptimisationModel) -> None:
        """
        Bind this handler to a solver model.

        Must be called before :meth:`add_variables` or any constraint method.

        :param model: The optimisation model
        :type model: OptimisationModel
        """
        self._model = model

    @abstractmethod
    def add_variables(self, times: Iterable[DateTime], max_power: Bound, min_power: Bound) -> None:
        """
        Declare all reserve temporal variables and create them for *times*.

        :param times: Timesteps
        :type times: Iterable[DateTime]
        :param max_power: Maximum power: a constant, a timeseries or a function of time
        :type max_power: Bound
        :param min_power: Minimum power, same forms as *max_power*
        :type min_power: Bound
        """

    def _declare(self, prefix: str, times: list[DateTime], lower_bound: Bound, upper_bound: Bound) -> TemporalVariable:
        """Declare the ``{prefix}_{name}`` temporal variable and create it for *times*."""
        return self._require_model().add_temporal_variable(
            f"{prefix}_{self._name}", times, lower_bound=lower_bound, upper_bound=upper_bound
        )

    def _require_model(self) -> OptimisationModel:
        if self._model is None:
            raise RuntimeError(
                f"{self.__class__.__name__}.setup() must be called before adding variables or constraints."
            )
        return self._model
