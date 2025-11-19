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
    This class is used to add and manage values to an OptimisationModel variable outside its time limits.
    Ex :
    model_var = ModelVar(
        lambda t: model.get_variable(t),
        lambda t: model.add_boolean_variable(t)
    )
    """

    def __init__(self, getter: Callable[[DateTime], Any], setter: Callable[[DateTime], Any]):
        self._getter = getter
        self._setter = setter
        self._extended_frame: dict[DateTime, int] = {}

    def get_value(self, t: DateTime) -> Any:
        """
        Get the value matching the DateTime key

        :param t: DateTime key

        :return: the value
        """
        if t in self._extended_frame:
            return self._extended_frame[t]
        else:
            return self.get_model_var(t)

    def get_extended_value(self, t: DateTime) -> int:
        """
        Get the value matching the DateTime key from the extended frame

        :param t: DateTime key

        :return: the value
        """
        return self._extended_frame[t]

    def set_extended(self, t: DateTime, value: int):
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
