"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pendulum import DateTime

from atlas.solver.solver_interface import OptimisationModel


class ReserveHandler(ABC):
    """
    Base class for reserve variable/constraint builders.

    Owns the canonical naming convention ``{prefix}_{name}_{time}`` and the
    model binding.  Equipment-specific variables and constraints are declared
    in subclasses.  Instances are not created directly — use
    :class:`ReserveFactory`.
    """

    def __init__(self, name: str, maximum_automated: float) -> None:
        self._name = name
        self._maximum_automated = maximum_automated
        self._model: OptimisationModel | None = None

    def setup(self, model: OptimisationModel) -> None:
        """
        Bind this handler to a solver model.

        Must be called before :meth:`add_variables` or any constraint method.

        :param model: The optimisation model
        :type model: OptimisationModel
        """
        self._model = model

    def var(self, prefix: str, time: DateTime) -> str:
        """
        Return the canonical variable name ``{prefix}_{name}_{time}``.

        :param prefix: Variable prefix (e.g. ``"reserves_up"``)
        :type prefix: str
        :param time: Timestep
        :type time: DateTime
        :return: Variable name
        :rtype: str
        """
        return f"{prefix}_{self._name}_{time}"

    @abstractmethod
    def add_variables(self, time: DateTime, max_power: float, min_power: float) -> None:
        """
        Register all reserve decision variables for *time*.

        :param time: Timestep
        :type time: DateTime
        :param max_power: Maximum power at *time*
        :type max_power: float
        :param min_power: Minimum power at *time*
        :type min_power: float
        """

    def _require_model(self) -> OptimisationModel:
        if self._model is None:
            raise RuntimeError(
                f"{self.__class__.__name__}.setup() must be called before adding variables or constraints."
            )
        return self._model
