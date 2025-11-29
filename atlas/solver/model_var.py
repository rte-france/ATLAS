"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Callable
from typing import Any

from pendulum import DateTime

import atlas.config as cfg


class ModelVar:
    """
    Manages OptimisationModel variables with extended time frame support.

    Provides access to model variables both within and outside the model's time limits
    by maintaining an extended frame for boundary values (e.g., initial conditions).

    Example:
        >>> power = ModelVar(
        ...     getter=lambda t: model.get_variable(f"power_{t}"),
        ...     setter=lambda t: model.add_continuous_variable(f"power_{t}", lb=0, ub=100)
        ... )
        >>> power.set_extended(t0, 50.0)  # Set initial condition
        >>> power.set_model_var(t1)  # Add variable to model
        >>> power.get_value(t0)  # Returns 50.0 from extended frame
        >>> power.get_value(t1)  # Returns model variable object
    """

    def __init__(self, getter: Callable[[DateTime], Any], setter: Callable[[DateTime], Any]):
        self._getter = getter
        self._setter = setter
        self._extended_frame: dict[DateTime, float] = {}

    def get_value(self, t: DateTime) -> Any:
        """
        Get the value matching the DateTime key

        :param t: DateTime key

        :return: Either the optimisation variable or the float value. First tries to get the float value.
        """
        if t in self._extended_frame:
            return self._extended_frame[t]
        else:
            return self.get_model_var(t)

    def get_extended_value(self, t: DateTime) -> float:
        """
        Get the value matching the DateTime key from the extended frame

        :param t: DateTime key
        :return: the value
        """
        return self._extended_frame[t]

    def set_extended(self, t: DateTime, value: float):
        """
        Set the given value in the extended frame

        :param t: DateTime key
        :param value: the value to set
        """
        self._extended_frame[t] = value
        # check for duplicates
        try:
            self.get_model_var(t)
            cfg.logger.error(f"The time {t} already exists.")
        except ValueError:
            pass  # the DateTime key doesn't exist in the model, as intended

    def get_model_var(self, t: DateTime) -> Any:
        """
        Get the variable objet from the OptimisationModel with the getter given to the class

        :param t: DateTime key

        :return: the model variable
        """
        return self._getter(t)

    def set_model_var(self, t: DateTime):
        """
        Set a variable objet in the OptimisationModel with the setter given to the class
        :param t: DateTime key
        """
        self._setter(t)
        # check for duplicates
        if t in self._extended_frame:
            cfg.logger.error(f"The time {t} already exists.")

    def __getstate__(self):
        """
        Remove callable attributes (getter, setter) from pickling.
        """
        state = self.__dict__.copy()
        state["_getter"] = None
        state["_setter"] = None
        return state

    def __setstate__(self, state):
        """
        Restore state after unpickling.
        User must later reassign getter and setter manually.
        """
        self.__dict__.update(state)
        self._getter = None
        self._setter = None
